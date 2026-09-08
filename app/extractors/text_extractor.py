import hashlib
from app.extractors.models import ExtractedContent


def extract_from_text(text: str) -> ExtractedContent:
    """
    Process plain text content and generate a deterministic SourceIdentifier hash.
    """
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("Text content cannot be empty.")

    # Compute SHA-256 hash of the plain text content for SourceIdentifier
    text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    source_identifier = f"hash:{text_hash[:16]}"

    # Extract first line or snippet for metadata title suggestion
    first_line = clean_text.splitlines()[0] if clean_text else ""
    suggested_title = first_line[:60] + ("..." if len(first_line) > 60 else "")

    return ExtractedContent(
        content_type="text",
        source_identifier=source_identifier,
        raw_text=clean_text,
        metadata={
            "suggested_title": suggested_title,
            "char_count": len(clean_text)
        }
    )
