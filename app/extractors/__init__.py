from typing import Union, Optional
from pathlib import Path
from app.extractors.models import ExtractedContent
from app.extractors.text_extractor import extract_from_text
from app.extractors.url_extractor import extract_from_url, is_valid_url
from app.extractors.pdf_extractor import extract_from_pdf


def extract_content(
    content_input: Union[str, bytes, Path],
    content_type_hint: Optional[str] = None,
    filename: Optional[str] = None
) -> ExtractedContent:
    """
    Unified router and extractor for Text, URL, and PDF inputs.
    """
    if content_type_hint == "pdf" or (isinstance(filename, str) and filename.lower().endswith(".pdf")):
        return extract_from_pdf(content_input, filename=filename)

    if isinstance(content_input, (bytes, Path)):
        return extract_from_pdf(content_input, filename=filename)

    text_str = str(content_input).strip()
    if content_type_hint == "url" or is_valid_url(text_str):
        return extract_from_url(text_str)

    return extract_from_text(text_str)


__all__ = [
    "ExtractedContent",
    "extract_content",
    "extract_from_text",
    "extract_from_url",
    "extract_from_pdf",
    "is_valid_url"
]
