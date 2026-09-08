import unittest
from unittest.mock import MagicMock, patch
from app.sheets import GoogleSheetsClient, REQUIRED_HEADERS
from app.llm import LLMContentResult


class TestGoogleSheetsModule(unittest.TestCase):
    def test_schema_header_contract(self):
        expected_schema = [
            "SourceIdentifier",
            "SubmissionTimestamp",
            "ContentType",
            "LLMTitle",
            "Rationale",
            "Category",
            "X_Variant",
            "LinkedIn_Variant"
        ]
        self.assertEqual(REQUIRED_HEADERS, expected_schema)

    def test_composite_key_building(self):
        client = GoogleSheetsClient()
        url = "https://example.com/blog/123"

        key_no_style = client.build_composite_key(url, style_hash=None)
        self.assertEqual(key_no_style, url)

        key_with_style = client.build_composite_key(url, style_hash="a1b2c3d4e5f6")
        self.assertEqual(key_with_style, "https://example.com/blog/123#style:a1b2c3d4e5f6")

    @patch.object(GoogleSheetsClient, "connect")
    def test_idempotent_duplicate_detection(self, mock_connect):
        mock_worksheet = MagicMock()
        mock_connect.return_value = mock_worksheet

        # Existing identifiers in Google Sheet
        mock_worksheet.col_values.return_value = [
            "SourceIdentifier",
            "https://example.com/article-1",
            "hash:abc1234567890def#style:pirate_v1"
        ]

        client = GoogleSheetsClient()

        # Duplicate check for exact existing URL
        self.assertTrue(client.is_duplicate("https://example.com/article-1"))

        # Duplicate check for new unique URL -> False
        self.assertFalse(client.is_duplicate("https://example.com/article-2"))

        # Duplicate check for existing URL when new style hash is set -> False (Requirement 10)
        self.assertFalse(client.is_duplicate("https://example.com/article-1", style_hash="haiku_v2"))

    @patch.object(GoogleSheetsClient, "connect")
    def test_append_content_row(self, mock_connect):
        mock_worksheet = MagicMock()
        mock_connect.return_value = mock_worksheet
        mock_worksheet.col_values.return_value = ["SourceIdentifier"]

        client = GoogleSheetsClient()

        dummy_llm_result = LLMContentResult(
            title="Sample Article Title",
            rationale="Great editorial summary.",
            category="Tech",
            x_variant="Short X draft under 280 chars.",
            linkedin_variant="Longer professional LinkedIn post content."
        )

        res = client.append_content_row(
            source_identifier="https://example.com/new-article",
            content_type="url",
            llm_result=dummy_llm_result
        )

        self.assertTrue(res["appended"])
        self.assertEqual(res["status"], "appended")
        mock_worksheet.append_row.assert_called_once()
        row_added = mock_worksheet.append_row.call_args[0][0]
        self.assertEqual(row_added[0], "https://example.com/new-article")
        self.assertEqual(row_added[2], "url")
        self.assertEqual(row_added[3], "Sample Article Title")


if __name__ == "__main__":
    unittest.main()
