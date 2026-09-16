import unittest
from unittest.mock import patch, MagicMock
from app.llm import (
    build_generation_prompt,
    parse_and_validate_llm_json,
    LLMContentResult,
    LLMClient
)


class TestLLMModule(unittest.TestCase):
    def test_prompt_construction_without_style(self):
        prompt = build_generation_prompt("Sample article text")
        self.assertIn("Sample article text", prompt["user"])
        self.assertNotIn("USER HOUSE STYLE DIRECTIVES", prompt["system"])

    def test_prompt_construction_with_style(self):
        style = "Write like a pirate with witty punchlines."
        prompt = build_generation_prompt("Sample article text", style_prompt=style)
        self.assertIn("USER HOUSE STYLE DIRECTIVES", prompt["system"])
        self.assertIn("Write like a pirate", prompt["system"])

    def test_json_parser_valid(self):
        raw_json = """
        {
          "title": "AI Breakthrough",
          "rationale": "Shows major advances in software.",
          "category": "Technology",
          "variants": {
            "x_post": "AI is changing everything fast!",
            "linkedin_post": "Artificial intelligence represents a fundamental shift..."
          }
        }
        """
        res = parse_and_validate_llm_json(raw_json)
        self.assertEqual(res.title, "AI Breakthrough")
        self.assertEqual(res.rationale, "Shows major advances in software.")
        self.assertEqual(res.category, "Technology")
        self.assertEqual(res.x_variant, "AI is changing everything fast!")
        self.assertEqual(res.linkedin_variant, "Artificial intelligence represents a fundamental shift...")

    def test_json_parser_markdown_wrapped_and_truncation(self):
        long_x_post = "A " * 200  # 400 characters long
        raw_response = f"""
        ```json
        {{
          "title": "Wrapped JSON",
          "rationale": "Testing markdown extraction",
          "category": "AI",
          "variants": {{
            "x_post": "{long_x_post}",
            "linkedin_post": "Long linkedin post text"
          }}
        }}
        ```
        """
        res = parse_and_validate_llm_json(raw_response)
        self.assertEqual(res.title, "Wrapped JSON")
        self.assertLessEqual(len(res.x_variant), 280)
        self.assertTrue(res.x_variant.endswith("..."))

    @patch("requests.post")
    def test_groq_llm_client_call(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"title":"Groq Title","rationale":"Rationale","category":"Tech","variants":{"x_post":"Short X","linkedin_post":"Long Linkedin"}}'
                    }
                }
            ]
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        client = LLMClient()
        client.groq_api_key = "gsk_testkey"
        client.primary_provider = "groq"

        result = client.generate_content("Test input text")
        self.assertEqual(result.title, "Groq Title")
        self.assertEqual(result.x_variant, "Short X")

    @patch("requests.post")
    def test_ollama_fallback(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "message": {
                "content": '{"title":"Ollama Title","rationale":"Rationale","category":"Tech","variants":{"x_post":"Ollama X","linkedin_post":"Ollama Linkedin"}}'
            }
        }
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        client = LLMClient()
        client.gemini_api_key = ""
        client.groq_api_key = ""  # No cloud keys -> falls back to Ollama
        client.primary_provider = "ollama"

        result = client.generate_content("Test input text")
        self.assertEqual(result.title, "Ollama Title")
        self.assertEqual(result.x_variant, "Ollama X")


if __name__ == "__main__":
    unittest.main()
