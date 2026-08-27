"""Small local-only Ollama transport for structured methodology extraction."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
STATUS_TIMEOUT_SECONDS = 2.0
GENERATION_TIMEOUT_SECONDS = 120.0


class LocalExtractionError(RuntimeError):
    """A stable local-engine failure that is safe to turn into UI state."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class OllamaClient:
    """Call only the loopback Ollama API; no configurable remote host exists."""

    def __init__(self, opener: Callable[..., Any] = urlopen):
        self._opener = opener

    def _json(self, request: Request, timeout: float) -> dict[str, Any]:
        try:
            with self._opener(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise LocalExtractionError("local_llm_unavailable") from exc
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            raise LocalExtractionError("local_llm_invalid_response") from exc
        if not isinstance(payload, dict):
            raise LocalExtractionError("local_llm_invalid_response")
        return payload

    def available(self, model: str) -> bool:
        request = Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        try:
            payload = self._json(request, STATUS_TIMEOUT_SECONDS)
        except LocalExtractionError:
            return False
        models = payload.get("models")
        if not isinstance(models, list):
            return False
        return any(
            isinstance(item, dict) and item.get("name") == model
            for item in models
        )

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
    ) -> str:
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
                "keep_alive": "5m",
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = self._json(request, GENERATION_TIMEOUT_SECONDS)
        message = payload.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LocalExtractionError("local_llm_invalid_response")
        return content
