from typing import Optional, Dict, Any

SYSTEM_PERSONA = """You are an expert editorial content strategist and social media copywriter.
Your task is to analyze the provided source content and generate structured, high-quality social media drafts and editorial metadata.

You must respond ONLY with a single valid JSON object adhering strictly to the following JSON schema:
{
  "title": "A concise, compelling title for the content",
  "rationale": "A one-sentence explanation of why this content is valuable or shareable",
  "category": "A single relevant category tag (e.g., 'AI', 'Startups', 'Productivity', 'Tech')",
  "variants": {
    "x_post": "A short, punchy draft optimized for X (Twitter). MUST BE STRICTLY UNDER 280 CHARACTERS.",
    "linkedin_post": "A professional, insightful longer-form post for LinkedIn, formatted with paragraph breaks or bullet points."
  }
}
"""


def build_generation_prompt(content_text: str, style_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Construct system and user messages for the LLM request.
    Injects custom user style prompt if provided.
    """
    system_instruction = SYSTEM_PERSONA

    if style_prompt and style_prompt.strip():
        system_instruction += f"\n\n[USER STYLE GUIDE PREFERENCE]\nApply the following style, tone, and formatting constraints to all generated text:\n\"{style_prompt.strip()}\""

    user_message = f"""Analyze the following source content and generate the requested JSON output:

--- SOURCE CONTENT START ---
{content_text.strip()}
--- SOURCE CONTENT END ---

Remember: Output ONLY valid JSON with keys "title", "rationale", "category", and "variants" ("x_post", "linkedin_post").
"""

    return {
        "system": system_instruction,
        "user": user_message
    }
