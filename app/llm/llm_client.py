import json
import time
import logging
import requests
from typing import Optional, Dict, Any, Callable
from app.config import settings
from app.llm.prompts import build_generation_prompt
from app.llm.parser import parse_and_validate_llm_json, LLMContentResult

logger = logging.getLogger(__name__)


def _make_request_with_backoff(request_func: Callable[[], requests.Response], max_retries: int = 3, initial_delay: float = 1.0) -> requests.Response:
    """
    Execute HTTP request with exponential backoff using time.sleep()
    to gracefully handle HTTP 429 (Too Many Requests) and transient errors.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            response = request_func()
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as err:
            status_code = err.response.status_code if err.response is not None else None
            if status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                retry_after = None
                if err.response is not None and "Retry-After" in err.response.headers:
                    try:
                        retry_after = float(err.response.headers["Retry-After"])
                    except ValueError:
                        pass
                sleep_time = retry_after if retry_after else delay
                logger.warning(
                    f"HTTP {status_code} Rate Limit / Transient Error (attempt {attempt}/{max_retries}). "
                    f"Retrying in {sleep_time:.1f}s with exponential backoff..."
                )
                time.sleep(sleep_time)
                delay *= 2
            else:
                raise
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_err:
            if attempt < max_retries:
                logger.warning(
                    f"Network Connection Error (attempt {attempt}/{max_retries}): {conn_err}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise

    raise RuntimeError("Max retries exceeded for LLM HTTP request.")


class LLMClient:
    """
    Multi-provider LLM client supporting Gemini, Groq, and local Ollama with fallback and rate-limit backoff logic.
    """

    def __init__(self):
        self.gemini_api_key = settings.GOOGLE_API_KEY
        self.groq_api_key = settings.GROQ_API_KEY
        self.ollama_model = settings.OLLAMA_MODEL
        self.primary_provider = settings.LLM_PROVIDER.lower()

    @property
    def ollama_base_url(self) -> str:
        return settings.effective_ollama_url

    def _is_valid_key(self, key: Optional[str]) -> bool:
        if not key:
            return False
        clean_key = key.strip()
        if not clean_key or clean_key.startswith("your_"):
            return False
        return True

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
        if self.primary_provider == "gemini" and self._is_valid_key(self.gemini_api_key):
            order.append("gemini")
        elif self.primary_provider == "groq" and self._is_valid_key(self.groq_api_key):
            order.append("groq")
        elif self.primary_provider == "ollama":
            order.append("ollama")

        # Add fallbacks
        for fallback in ["gemini", "groq", "ollama"]:
            if fallback not in order:
                if fallback == "gemini" and self._is_valid_key(self.gemini_api_key):
                    order.append(fallback)
                elif fallback == "groq" and self._is_valid_key(self.groq_api_key):
                    order.append(fallback)
                elif fallback == "ollama":
                    order.append(fallback)

        if not order:
            order = ["ollama"]  # Default local fallback

        return order

    def _call_provider(self, provider: str, prompt_dict: Dict[str, str]) -> str:
        if provider == "groq":
            return self._call_groq(prompt_dict)
        elif provider == "gemini":
            return self._call_gemini(prompt_dict)
        elif provider == "ollama":
            return self._call_ollama(prompt_dict)
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    def _call_groq(self, prompt_dict: Dict[str, str]) -> str:
        """Call Groq API via OpenAI-compatible endpoint with dynamic model discovery and rate-limit exponential backoff."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }

        # Dynamically fetch active chat models for this Groq account
        candidate_models = []
        try:
            models_res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            if models_res.status_code == 200:
                data = models_res.json().get("data", [])
                for m in data:
                    m_id = m.get("id", "")
                    if m_id and not any(x in m_id.lower() for x in ["whisper", "guard", "orpheus", "canopylabs"]):
                        candidate_models.append(m_id)
        except Exception as e:
            logger.warning(f"Could not dynamically list Groq models: {e}")

        # Fallback list if dynamic fetch is empty
        fallback_list = [
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b",
            "groq/compound-mini",
            "llama-3.1-8b-instant",
            "llama3-70b-8192",
            "mixtral-8x7b-32768"
        ]
        for fb in fallback_list:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_err = None
        for model_name in candidate_models:
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": prompt_dict["system"]},
                    {"role": "user", "content": prompt_dict["user"]}
                ],
                "temperature": 0.3
            }
            try:
                logger.info(f"Sending request to Groq API using model '{model_name}'...")
                response = _make_request_with_backoff(lambda: requests.post(url, headers=headers, json=payload, timeout=45))
                data = response.json()
                choice_msg = data["choices"][0]["message"]
                content = choice_msg.get("content") or choice_msg.get("reasoning") or ""
                if content and content.strip():
                    return content
            except Exception as req_err:
                logger.warning(f"Groq model '{model_name}' returned error ({req_err}). Trying next Groq model...")
                last_err = req_err
                continue

        raise RuntimeError(f"Groq API failed across candidate models. Last error: {last_err}")

    def _call_gemini(self, prompt_dict: Dict[str, str]) -> str:
        """Call Google Gemini API with rate-limit exponential backoff and candidate model fallback."""
        candidate_models = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-flash-latest"]
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

        last_err = None
        for model_name in candidate_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
            try:
                logger.info(f"Sending request to Gemini API using model '{model_name}'...")
                response = _make_request_with_backoff(lambda: requests.post(url, headers=headers, json=payload, timeout=45))
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if text and text.strip():
                    return text
            except Exception as err:
                logger.warning(f"Gemini model '{model_name}' returned error ({err}). Trying next Gemini model...")
                last_err = err
                continue

        raise RuntimeError(f"Gemini API failed across candidate models. Last error: {last_err}")

    def _call_ollama(self, prompt_dict: Dict[str, str]) -> str:
        """Call local Ollama API with rate-limit exponential backoff."""
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
        response = _make_request_with_backoff(lambda: requests.post(url, json=payload, timeout=90))
        data = response.json()
        return data["message"]["content"]


llm_client = LLMClient()
