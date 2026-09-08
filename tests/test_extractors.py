import unittest
from unittest.mock import patch, MagicMock
from app.extractors import (
    extract_content,
    extract_from_text,
    extract_from_url,
    extract_from_pdf,
    is_valid_url
)


class TestExtractors(unittest.TestCase):
    def test_text_extractor(self):
        text = "Artificial Intelligence is transforming software development."
        result = extract_from_text(text)

        self.assertEqual(result.content_type, "text")
        self.assertTrue(result.source_identifier.startswith("hash:"))
        self.assertEqual(result.raw_text, text)
        self.assertIn("char_count", result.metadata)

    def test_url_validation(self):
        self.assertTrue(is_valid_url("https://example.com/article/123"))
        self.assertTrue(is_valid_url("http://github.com/microsoft/markitdown"))
        self.assertFalse(is_valid_url("AI is transforming software development."))

    @patch("trafilatura.fetch_url")
    @patch("trafilatura.extract")
    @patch("trafilatura.extract_metadata")
    def test_url_extractor(self, mock_metadata, mock_extract, mock_fetch):
        url = "https://example.com/tech-news"
        mock_fetch.return_value = "<html><body><h1>Tech News</h1><p>Content</p></body></html>"
        mock_extract.return_value = "Tech News\nContent"

        mock_meta = MagicMock()
        mock_meta.title = "Tech News Article"
        mock_metadata.return_value = mock_meta

        result = extract_from_url(url)

        self.assertEqual(result.content_type, "url")
        self.assertEqual(result.source_identifier, url)
        self.assertEqual(result.raw_text, "Tech News\nContent")
        self.assertEqual(result.metadata["title"], "Tech News Article")

    @patch("markitdown.MarkItDown.convert")
    def test_pdf_extractor(self, mock_convert):
        mock_result = MagicMock()
        mock_result.text_content = "# PDF Header\n\nThis is sample PDF text content."
        mock_convert.return_value = mock_result

        sample_bytes = b"%PDF-1.4 sample pdf content bytes"
        result = extract_from_pdf(sample_bytes, filename="report.pdf")

        self.assertEqual(result.content_type, "pdf")
        self.assertTrue(result.source_identifier.startswith("hash:"))
        self.assertIn("PDF Header", result.raw_text)
        self.assertEqual(result.metadata["filename"], "report.pdf")

    def test_unified_router(self):
        # Plain text input
        res_text = extract_content("Simple text message to process")
        self.assertEqual(res_text.content_type, "text")

        # PDF input with filename
        with patch("markitdown.MarkItDown.convert") as mock_convert:
            mock_result = MagicMock()
            mock_result.text_content = "# PDF Title\n\nDocument details."
            mock_convert.return_value = mock_result

            res_pdf = extract_content(b"%PDF-1.4 sample", filename="test.pdf")
            self.assertEqual(res_pdf.content_type, "pdf")


if __name__ == "__main__":
    unittest.main()
