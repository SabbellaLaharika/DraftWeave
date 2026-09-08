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


class GoogleSheetsClient:
    """
    Google Sheets API client handling connection, worksheet creation,
    header verification, and idempotent row appending.
    """

    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self.sheet_name = settings.GOOGLE_SHEET_NAME
        self._client: Optional[gspread.Client] = None
        self._worksheet: Optional[gspread.Worksheet] = None

    def _get_credentials(self) -> Credentials:
        """Load service account credentials from Base64 env var or JSON file."""
        if settings.GOOGLE_SHEETS_CREDENTIALS_B64:
            try:
                decoded_json = base64.b64decode(settings.GOOGLE_SHEETS_CREDENTIALS_B64).decode("utf-8")
                creds_dict = json.loads(decoded_json)
                return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            except Exception as e:
                logger.error(f"Failed to load credentials from GOOGLE_SHEETS_CREDENTIALS_B64: {e}")

        if settings.GOOGLE_SHEETS_CREDENTIALS_JSON:
            try:
                return Credentials.from_service_account_file(settings.GOOGLE_SHEETS_CREDENTIALS_JSON, scopes=SCOPES)
            except Exception as e:
                logger.error(f"Failed to load credentials from JSON file: {e}")

        raise ValueError("Google Sheets credentials not provided or invalid.")

    def connect(self) -> gspread.Worksheet:
        """Authenticate and open/initialize the target worksheet."""
        if self._worksheet:
            return self._worksheet

        creds = self._get_credentials()
        self._client = gspread.authorize(creds)

        # Open spreadsheet by ID or Name
        if self.sheet_id:
            spreadsheet = self._client.open_by_key(self.sheet_id)
        elif self.sheet_name:
            spreadsheet = self._client.open(self.sheet_name)
        else:
            raise ValueError("Neither GOOGLE_SHEET_ID nor GOOGLE_SHEET_NAME is configured.")

        # Open or create 'Content' worksheet
        try:
            worksheet = spreadsheet.worksheet("Content")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Content", rows=100, cols=len(REQUIRED_HEADERS))

        # Ensure header row exists
        existing_headers = worksheet.row_values(1)
        if not existing_headers:
            worksheet.append_row(REQUIRED_HEADERS)
        elif existing_headers != REQUIRED_HEADERS:
            logger.warning(f"Worksheet headers mismatch. Updating header row to standard schema.")
            worksheet.update('A1:H1', [REQUIRED_HEADERS])

        self._worksheet = worksheet
        return worksheet

    def get_existing_identifiers(self) -> List[str]:
        """Fetch all values in the SourceIdentifier column (Column A)."""
        worksheet = self.connect()
        # Fetch column 1 (SourceIdentifier) starting from row 2
        col_values = worksheet.col_values(1)
        return col_values[1:] if len(col_values) > 1 else []

    def build_composite_key(self, source_identifier: str, style_hash: Optional[str] = None) -> str:
        """
        Build composite key incorporating style hash to support Requirement 10
        (re-submitting same content under a new style prompt creates a new row).
        """
        if style_hash:
            return f"{source_identifier}#style:{style_hash}"
        return source_identifier

    def is_duplicate(self, source_identifier: str, style_hash: Optional[str] = None) -> bool:
        """Check if source_identifier (or composite key) already exists in Google Sheet."""
        composite_key = self.build_composite_key(source_identifier, style_hash)
        existing_keys = self.get_existing_identifiers()
        return composite_key in existing_keys

    def append_content_row(
        self,
        source_identifier: str,
        content_type: str,
        llm_result: LLMContentResult,
        style_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Append a new row idempotently to Google Sheets.
        Returns dict with status ('appended' or 'duplicate').
        """
        composite_key = self.build_composite_key(source_identifier, style_hash)

        if self.is_duplicate(source_identifier, style_hash):
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
        worksheet.append_row(new_row)
        logger.info(f"Successfully appended row for '{composite_key}' to Google Sheets.")

        return {
            "status": "appended",
            "source_identifier": source_identifier,
            "composite_key": composite_key,
            "appended": True,
            "row": new_row
        }


sheets_client = GoogleSheetsClient()
