"""Small OpenAI-compatible HTTP client.

The generator intentionally avoids the OpenAI Python package so it runs inside
the repository Apptainer image without extra Python dependencies.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class LLMClientError(RuntimeError):
    """Raised when the OpenAI-compatible endpoint rejects a request."""


@dataclass
class LLMResponse:
    content: str
    raw: dict[str, Any]
    model: str


class LLMClient:
    def __init__(
        self,
        endpoint: str,
        model: str | None = None,
        api_key: str | None = None,
        timeout: int = 600,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_body = extra_body or {}

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request_json(
        self, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.endpoint}{path}"
        data = None
        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            method = "POST"
        req = urllib.request.Request(
            url, data=data, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMClientError(f"{url} returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise LLMClientError(f"{url} request failed: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"{url} returned non-JSON response: {body}") from exc
        if isinstance(parsed, dict) and "error" in parsed:
            raise LLMClientError(f"{url} returned error: {parsed['error']}")
        if not isinstance(parsed, dict):
            raise LLMClientError(f"{url} returned unexpected JSON: {parsed!r}")
        return parsed

    def list_models(self) -> list[str]:
        parsed = self._request_json("/models")
        names: list[str] = []
        for item in parsed.get("data", []):
            if isinstance(item, dict) and item.get("id"):
                names.append(str(item["id"]))
        for item in parsed.get("models", []):
            if not isinstance(item, dict):
                continue
            name = item.get("model") or item.get("name") or item.get("id")
            if name:
                names.append(str(name))
        deduped: list[str] = []
        seen: set[str] = set()
        for name in names:
            if name not in seen:
                seen.add(name)
                deduped.append(name)
        return deduped

    def resolve_model(self) -> str:
        if self.model:
            return self.model
        models = self.list_models()
        if not models:
            raise LLMClientError("endpoint did not return any models")
        self.model = models[0]
        return self.model

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 16384,
    ) -> LLMResponse:
        model = self.resolve_model()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        payload.update(self.extra_body)
        parsed = self._request_json("/chat/completions", payload)
        choices = parsed.get("choices")
        if not choices:
            raise LLMClientError(f"chat response has no choices: {parsed!r}")
        choice0 = choices[0]
        if not isinstance(choice0, dict):
            raise LLMClientError(f"unexpected choice format: {choice0!r}")
        message = choice0.get("message", {})
        if not isinstance(message, dict):
            raise LLMClientError(f"unexpected message format: {message!r}")
        content = str(message.get("content") or "")
        if not content and message.get("reasoning_content"):
            content = str(message["reasoning_content"])
        return LLMResponse(content=content, raw=parsed, model=model)
