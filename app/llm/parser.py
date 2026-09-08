import json
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class LLMContentResult:
    title: str
    rationale: str
    category: str
    x_variant: str
    linkedin_variant: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "rationale": self.rationale,
            "category": self.category,
            "x_variant": self.x_variant,
            "linkedin_variant": self.linkedin_variant
        }


def extract_json_block(raw_response: str) -> str:
    """Extract JSON content from LLM response string even if wrapped in ```json markdown blocks."""
    cleaned = raw_response.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Find first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace:last_brace + 1].strip()

    return cleaned


def parse_and_validate_llm_json(raw_response: str) -> LLMContentResult:
    """
    Parse raw string output from LLM, validate JSON structure, and enforce constraints.
    """
    json_str = extract_json_block(raw_response)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}\nRaw output: {raw_response[:200]}")

    title = str(data.get("title", "")).strip()
    rationale = str(data.get("rationale", "")).strip()
    category = str(data.get("category", "")).strip()

    variants = data.get("variants", {})
    if not isinstance(variants, dict):
        variants = {}

    x_post = str(variants.get("x_post") or data.get("x_post") or data.get("X_Variant") or "").strip()
    linkedin_post = str(variants.get("linkedin_post") or data.get("linkedin_post") or data.get("LinkedIn_Variant") or "").strip()

    # Fallbacks if fields are empty
    if not title:
        title = "Untitled Summary"
    if not rationale:
        rationale = "Generated overview based on submitted source content."
    if not category:
        category = "General"
    if not linkedin_post:
        linkedin_post = x_post or "Content summary unavailable."

    # Enforce X_Variant length <= 280 characters
    if len(x_post) > 280:
        # Truncate to 277 chars + "..."
        x_post = x_post[:277].rsplit(" ", 1)[0] + "..."
        if len(x_post) > 280:
            x_post = x_post[:280]

    return LLMContentResult(
        title=title,
        rationale=rationale,
        category=category,
        x_variant=x_post,
        linkedin_variant=linkedin_post
    )
