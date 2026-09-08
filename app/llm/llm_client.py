import json
import logging
import requests
from typing import Optional, Dict, Any
from app.config import settings
from app.llm.prompts import build_generation_prompt
from app.llm.parser import parse_and_validate_llm_json, LLMContentResult

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Multi-provider LLM client supporting NVIDIA API, Gemini, Groq, and local Ollama with fallback logic.
    """

    def __init__(self):
        self.nvidia_api_key = settings.NVIDIA_API_KEY
        self.nvidia_model = settings.NVIDIA_MODEL
        self.gemini_api_key = settings.GOOGLE_API_KEY
        self.groq_api_key = settings.GROQ_API_KEY
        self.ollama_base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.ollama_model = settings.OLLAMA_MODEL
        self.primary_provider = settings.LLM_PROVIDER.lower()

    def generate_content(self, content_text: str, style_prompt: Optional[str] = None) -> LLMContentResult:
        """
        Generate structured LLM content using primary provider with fallback and retry logic.
        """
        prompt_dict = build_generation_prompt(content_text, style_prompt)
        providers_to_try = self._get_provider_order()

        last_exception = None

        for provider in providers_to_try:
            logger.info(f"Attempting content generation using LLM provider: {provider}")
            try:
                raw_response = self._call_provider(provider, prompt_dict)
                result = parse_and_validate_llm_json(raw_response)
                logger.info(f"Successfully generated structured content using {provider}")
                return result
            except Exception as e:
                logger.warning(f"Provider {provider} failed or returned invalid JSON: {e}")
                last_exception = e
                # Retry with corrective prompt if response was malformed
                try:
                    logger.info(f"Retrying provider {provider} with corrective JSON prompt...")
                    corrective_prompt = {
                        "system": prompt_dict["system"] + "\n\nCRITICAL: Your previous output was invalid. Return ONLY pure valid JSON.",
                        "user": prompt_dict["user"]
                    }
                    raw_response = self._call_provider(provider, corrective_prompt)
                    return parse_and_validate_llm_json(raw_response)
                except Exception as retry_err:
                    logger.warning(f"Retry on {provider} failed: {retry_err}")
                    last_exception = retry_err
                    continue

        raise RuntimeError(f"All LLM providers failed to generate valid content. Last error: {last_exception}")

    def _get_provider_order(self) -> list:
        order = []
        if self.primary_provider == "nvidia" and self.nvidia_api_key:
            order.append("nvidia")
        elif self.primary_provider == "groq" and self.groq_api_key:
            order.append("groq")
        elif self.primary_provider == "gemini" and self.gemini_api_key:
            order.append("gemini")
        elif self.primary_provider == "ollama":
            order.append("ollama")

        # Add fallbacks
        for fallback in ["nvidia", "gemini", "groq", "ollama"]:
            if fallback not in order:
                if fallback == "nvidia" and self.nvidia_api_key:
                    order.append(fallback)
                elif fallback == "gemini" and self.gemini_api_key:
                    order.append(fallback)
                elif fallback == "groq" and self.groq_api_key:
                    order.append(fallback)
                elif fallback == "ollama":
                    order.append(fallback)

        if not order:
            order = ["ollama"]  # Default local fallback

        return order

    def _call_provider(self, provider: str, prompt_dict: Dict[str, str]) -> str:
        if provider == "nvidia":
            return self._call_nvidia(prompt_dict)
        elif provider == "groq":
            return self._call_groq(prompt_dict)
        elif provider == "gemini":
            return self._call_gemini(prompt_dict)
        elif provider == "ollama":
            return self._call_ollama(prompt_dict)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _call_nvidia(self, prompt_dict: Dict[str, str]) -> str:
        """Call NVIDIA NIM API via OpenAI-compatible endpoint."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.nvidia_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.nvidia_model,
            "messages": [
                {"role": "system", "content": prompt_dict["system"]},
                {"role": "user", "content": prompt_dict["user"]}
            ],
            "temperature": 0.3,
            "max_tokens": 1024
        }
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _call_groq(self, prompt_dict: Dict[str, str]) -> str:
        """Call Groq API via OpenAI-compatible endpoint."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": prompt_dict["system"]},
                {"role": "user", "content": prompt_dict["user"]}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt_dict: Dict[str, str]) -> str:
        """Call Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "system_instruction": {
                "parts": [{"text": prompt_dict["system"]}]
            },
            "contents": [
                {"parts": [{"text": prompt_dict["user"]}]}
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.3
            }
        }
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _call_ollama(self, prompt_dict: Dict[str, str]) -> str:
        """Call local Ollama API."""
        url = f"{self.ollama_base_url}/api/chat"
        payload = {
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": prompt_dict["system"]},
                {"role": "user", "content": prompt_dict["user"]}
            ],
            "format": "json",
            "stream": False
        }
        response = requests.post(url, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]


llm_client = LLMClient()
