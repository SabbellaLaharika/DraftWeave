import time
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import gspread
from google.oauth2.service_account import Credentials
from app.config import settings
from app.llm.parser import LLMContentResult

logger = logging.getLogger(__name__)

REQUIRED_HEADERS = [
    "SourceIdentifier",
    "SubmissionTimestamp",
    "ContentType",
    "LLMTitle",
    "Rationale",
    "Category",
    "X_Variant",
    "LinkedIn_Variant"
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def _execute_with_backoff(api_func: Any, max_retries: int = 3, initial_delay: float = 2.0) -> Any:
    """
    Execute Google Sheets API operations with exponential backoff using time.sleep()
    to handle HTTP 429 Too Many Requests rate-limiting and quota errors.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return api_func()
        except gspread.exceptions.APIError as api_err:
            status_code = getattr(api_err.response, "status_code", None)
            is_rate_limit = status_code == 429 or "RESOURCE_EXHAUSTED" in str(api_err) or "quota" in str(api_err).lower()
            if is_rate_limit and attempt < max_retries:
                logger.warning(
                    f"Google Sheets HTTP 429 Rate Limit hit (attempt {attempt}/{max_retries}). "
                    f"Retrying in {delay:.1f}s with exponential backoff..."
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise
        except Exception as err:
            if attempt < max_retries and ("429" in str(err) or "quota" in str(err).lower()):
                logger.warning(
                    f"Google Sheets transient rate-limit error (attempt {attempt}/{max_retries}): {err}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise


class GoogleSheetsClient:
    """
    Google Sheets API client handling connection, worksheet creation,
    header verification, and idempotent row appending with 429 rate limit backoff.
    """

    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self.sheet_name = settings.GOOGLE_SHEET_NAME
        self._client: Optional[gspread.Client] = None
        self._worksheet: Optional[gspread.Worksheet] = None

    def _get_credentials(self) -> Credentials:
        """Load service account credentials from Base64 env var or JSON file."""
        b64_val = (settings.GOOGLE_SHEETS_CREDENTIALS_B64 or "").strip()
        if b64_val and not b64_val.startswith("your_"):
            try:
                decoded_json = base64.b64decode(b64_val).decode("utf-8")
                creds_dict = json.loads(decoded_json)
                return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            except Exception as e:
                logger.error(f"Failed to load credentials from GOOGLE_SHEETS_CREDENTIALS_B64: {e}")

        json_path = (settings.GOOGLE_SHEETS_CREDENTIALS_JSON or "").strip()
        if json_path:
            try:
                return Credentials.from_service_account_file(json_path, scopes=SCOPES)
            except Exception as e:
                logger.error(f"Failed to load credentials from JSON file '{json_path}': {e}")

        raise ValueError("Google Sheets credentials not provided or invalid.")

    def connect(self) -> gspread.Worksheet:
        """Authenticate and open/initialize the target worksheet."""
        if self._worksheet:
            return self._worksheet

        creds = self._get_credentials()
        self._client = gspread.authorize(creds)

        # Open spreadsheet by ID or Name (automatically create if not found)
        sheet_id_val = (self.sheet_id or "").strip()
        sheet_name_val = (self.sheet_name or "").strip()

        if sheet_id_val and not sheet_id_val.startswith("your_"):
            spreadsheet = self._client.open_by_key(sheet_id_val)
        elif sheet_name_val and not sheet_name_val.startswith("your_"):
            try:
                spreadsheet = self._client.open(sheet_name_val)
            except gspread.SpreadsheetNotFound:
                logger.info(f"Spreadsheet '{sheet_name_val}' not found. Automatically creating a new Google Sheet...")
                spreadsheet = self._client.create(sheet_name_val)
        else:
            # Default fallback sheet name
            fallback_name = "DraftWeave Content"
            try:
                spreadsheet = self._client.open(fallback_name)
            except gspread.SpreadsheetNotFound:
                logger.info(f"Creating fallback Google Sheet '{fallback_name}'...")
                spreadsheet = self._client.create(fallback_name)

        # Open or create 'Content' worksheet
        try:
            worksheet = spreadsheet.worksheet("Content")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Content", rows=100, cols=len(REQUIRED_HEADERS))

        # Ensure header row exists
        existing_headers = _execute_with_backoff(lambda: worksheet.row_values(1))
        if not existing_headers:
            _execute_with_backoff(lambda: worksheet.append_row(REQUIRED_HEADERS))
        elif existing_headers != REQUIRED_HEADERS:
            logger.warning(f"Worksheet headers mismatch. Updating header row to standard schema.")
            _execute_with_backoff(lambda: worksheet.update('A1:H1', [REQUIRED_HEADERS]))

        self._worksheet = worksheet
        return worksheet

    def get_existing_identifiers(self) -> List[str]:
        """Fetch all values in the SourceIdentifier column (Column A) with backoff."""
        worksheet = self.connect()
        # Fetch column 1 (SourceIdentifier) starting from row 2
        col_values = _execute_with_backoff(lambda: worksheet.col_values(1))
        return col_values[1:] if len(col_values) > 1 else []

    def get_user_hash(self, user_id: Optional[int]) -> Optional[str]:
        """Generate short SHA-256 hash of user ID for privacy-preserving user isolation."""
        if not user_id:
            return None
        import hashlib
        return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:8]

    def build_composite_key(
        self,
        source_identifier: str,
        style_hash: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> str:
        """
        Build composite key incorporating user hash and style hash to support multi-user isolation
        and style re-submissions:
        Format: usr:<user_hash>#<source_identifier>#style:<style_hash>
        """
        key = source_identifier
        if user_id:
            u_hash = self.get_user_hash(user_id)
            key = f"usr:{u_hash}#{key}"
        if style_hash:
            key = f"{key}#style:{style_hash}"
        return key

    def is_duplicate(
        self,
        source_identifier: str,
        style_hash: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> bool:
        """Check if source_identifier (or composite key) already exists in Google Sheet."""
        composite_key = self.build_composite_key(source_identifier, style_hash=style_hash, user_id=user_id)
        existing_keys = self.get_existing_identifiers()
        return composite_key in existing_keys

    def find_cached_llm_result(
        self,
        source_identifier: str,
        style_hash: Optional[str] = None
    ) -> Optional[LLMContentResult]:
        """
        Search existing Google Sheet rows for previously generated content matching
        the same source_identifier and style_hash from ANY user.
        If found, returns cached LLMContentResult to avoid redundant LLM calls!
        """
        try:
            worksheet = self.connect()
            all_records = _execute_with_backoff(lambda: worksheet.get_all_values())
            if len(all_records) <= 1:
                return None

            target_style_suffix = f"#style:{style_hash}" if style_hash else ""

            for row in reversed(all_records[1:]):  # Search backwards for latest match
                if not row or len(row) < 8:
                    continue
                key_in_row = row[0]  # Column A: SourceIdentifier composite key

                if source_identifier in key_in_row:
                    if style_hash and not key_in_row.endswith(target_style_suffix):
                        continue
                    if not style_hash and "#style:" in key_in_row:
                        continue

                    title = row[3]
                    rationale = row[4]
                    category = row[5]
                    x_variant = row[6]
                    linkedin_variant = row[7]

                    if title and x_variant and linkedin_variant:
                        logger.info(f"Found cached LLM draft in Google Sheets for '{source_identifier}' under style '{style_hash}'. Skipping LLM API call.")
                        return LLMContentResult(
                            title=title,
                            rationale=rationale,
                            category=category,
                            x_variant=x_variant,
                            linkedin_variant=linkedin_variant
                        )
        except Exception as e:
            logger.warning(f"Failed to search cached LLM result from Google Sheets: {e}")

        return None

    def append_content_row(
        self,
        source_identifier: str,
        content_type: str,
        llm_result: LLMContentResult,
        style_hash: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Append a new row idempotently to Google Sheets.
        Returns dict with status ('appended' or 'duplicate').
        """
        composite_key = self.build_composite_key(source_identifier, style_hash=style_hash, user_id=user_id)

        if self.is_duplicate(source_identifier, style_hash=style_hash, user_id=user_id):
            logger.info(f"Duplicate entry detected for key '{composite_key}'. Skipping Google Sheets append.")
            return {
                "status": "duplicate",
                "source_identifier": source_identifier,
                "composite_key": composite_key,
                "appended": False
            }

        timestamp_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_row = [
            composite_key,
            timestamp_iso,
            content_type,
            llm_result.title,
            llm_result.rationale,
            llm_result.category,
            llm_result.x_variant,
            llm_result.linkedin_variant
        ]

        worksheet = self.connect()
        _execute_with_backoff(lambda: worksheet.append_row(new_row))
        logger.info(f"Successfully appended row for '{composite_key}' to Google Sheets.")

        return {
            "status": "appended",
            "source_identifier": source_identifier,
            "composite_key": composite_key,
            "appended": True,
            "row": new_row
        }


sheets_client = GoogleSheetsClient()
