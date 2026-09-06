# OpenRouter LLM provider — OpenAI-compatible chat-completions via raw httpx.
#
# Rationale: no OpenAI/Anthropic SDK dependency. OpenRouter exposes an OpenAI-
# compatible POST /chat/completions endpoint, so a single httpx call covers any
# model. httpx is async-native (unlike yfinance/feedparser), so we do NOT wrap
# it in asyncio.to_thread.

import httpx

from app.providers.llm_base import LLMError, LLMProvider, LLMResult


class OpenRouterProvider(LLMProvider):
    """LLM source backed by an OpenAI-compatible chat-completions endpoint.

    The endpoint is determined by `base_url` (OpenRouter's API by default) and
    the model by `model`. If `api_key` is empty the caller should never
    construct this provider — the narrative service short-circuits to the
    rule-based fallback instead.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "",
        timeout: float = 30.0,
        temperature: float = 0.2,
        max_tokens: int = 300,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _payload(self, system: str, user: str) -> dict:
        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature,  # low: narrate facts, do not improvise
            "max_tokens": self._max_tokens,
        }

    async def model_available(self) -> bool:
        """True if the configured model is currently served by OpenRouter.

        Uses the public GET /models catalog (network call). A failure to
        reach the catalog returns False so the caller can fall back instead
        of spending a doomed completion request.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except httpx.HTTPError:
            return False
        if resp.status_code != 200:
            return False
        try:
            payload = resp.json()
            ids = {m.get("id") for m in payload.get("data", [])}
        except (ValueError, AttributeError):
            return False
        return self._model in ids

    @staticmethod
    def _parse_text(payload: dict, model: str) -> str:
        """Pull the assistant text from an OpenAI-compatible body."""
        try:
            choices = payload["choices"]
            text = choices[0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"malformed LLM response (no choices/content): {exc}")
        if not isinstance(text, str) or not text.strip():
            raise LLMError("malformed LLM response (empty text)")
        return text.strip()

    @staticmethod
    def _parse_tokens(payload: dict) -> int | None:
        usage = payload.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int):
                return total
        return None

    async def generate(self, system: str, user: str) -> LLMResult:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    self._endpoint(), json=self._payload(system, user), headers=headers
                )
        except httpx.HTTPError as exc:  # network / timeouts / connection errors
            raise LLMError(f"LLM request failed: {exc}")

        if resp.status_code != 200:
            # Non-2xx: surface a clean error so the caller can fall back. The
            # status is preserved (e.g. 403 = rejected by an OpenRouter
            # guardrail such as prompt-injection detection) without exposing
            # the response body, which may carry provider-internal details.
            raise LLMError(
                f"LLM returned HTTP {resp.status_code}", status_code=resp.status_code
            )

        try:
            payload = resp.json()
        except ValueError as exc:  # body not valid JSON
            raise LLMError(f"malformed LLM response (invalid JSON): {exc}")

        text = self._parse_text(payload, self._model)
        tokens = self._parse_tokens(payload)
        # Echo the provider's model name when present, else the configured one.
        model = payload.get("model") or self._model
        return LLMResult(text=text, tokens_used=tokens, model=model)