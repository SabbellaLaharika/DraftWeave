import os
import hashlib
import logging
from typing import Union, Optional
from pathlib import Path
from markitdown import MarkItDown
from app.extractors.models import ExtractedContent

logger = logging.getLogger(__name__)


def extract_from_pdf(pdf_source: Union[str, Path, bytes], filename: Optional[str] = None) -> ExtractedContent:
    """
    Extract structured Markdown content from a PDF using microsoft/markitdown.
    Accepts either a file path or raw PDF bytes.
    """
    pdf_bytes: bytes = b""
    temp_path: Optional[Path] = None

    if isinstance(pdf_source, (str, Path)):
        path = Path(pdf_source)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        file_path_to_convert = str(path)
        display_filename = filename or path.name
    elif isinstance(pdf_source, bytes):
        pdf_bytes = pdf_source
        display_filename = filename or "document.pdf"
        # Save temporary file for MarkItDown processing if needed
        temp_path = Path(f"temp_{hashlib.md5(pdf_bytes).hexdigest()[:8]}.pdf")
        with open(temp_path, "wb") as f:
            f.write(pdf_bytes)
        file_path_to_convert = str(temp_path)
    else:
        raise ValueError("pdf_source must be a file path or bytes.")

    try:
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
        source_identifier = f"hash:{pdf_hash[:16]}"

        # Process with MarkItDown
        markitdown_client = MarkItDown()
        result = markitdown_client.convert(file_path_to_convert)

        extracted_text = result.text_content if result else ""
        if not extracted_text or not extracted_text.strip():
            raise ValueError(f"Failed to extract text from PDF: {display_filename}")

        return ExtractedContent(
            content_type="pdf",
            source_identifier=source_identifier,
            raw_text=extracted_text.strip(),
            metadata={
                "filename": display_filename,
                "char_count": len(extracted_text.strip())
            }
        )
    finally:
        if temp_path and temp_path.exists():
            try:
                os.remove(temp_path)
            except OSError:
                pass
