import re
import logging
import trafilatura
from app.extractors.models import ExtractedContent

logger = logging.getLogger(__name__)

# Basic URL validation regex
URL_REGEX = re.compile(
    r"^(?:http|ftp)s?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
    r"localhost|"  # localhost...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$", re.IGNORECASE
)


def is_valid_url(url: str) -> bool:
    """Check if string is a valid HTTP/HTTPS URL."""
    return bool(URL_REGEX.match(url.strip()))


def extract_from_url(url: str) -> ExtractedContent:
    """
    Extract article content from a web URL using trafilatura.
    """
    clean_url = url.strip()
    if not is_valid_url(clean_url):
        raise ValueError(f"Invalid URL provided: {clean_url}")

    downloaded = trafilatura.fetch_url(clean_url)
    if not downloaded:
        raise ValueError(f"Failed to fetch content from URL: {clean_url}")

    # Extract clean text and metadata
    extracted_text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        no_fallback=False
    )

    if not extracted_text or not extracted_text.strip():
        raise ValueError(f"Could not extract meaningful article content from URL: {clean_url}")

    clean_text = extracted_text.strip()
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000]

    # Try extracting metadata (e.g. title) via trafilatura metadata extraction
    metadata_obj = trafilatura.extract_metadata(downloaded)
    title = metadata_obj.title if (metadata_obj and metadata_obj.title) else ""

    return ExtractedContent(
        content_type="url",
        source_identifier=clean_url,
        raw_text=clean_text,
        metadata={
            "title": title,
            "url": clean_url,
            "char_count": len(clean_text)
        }
    )
