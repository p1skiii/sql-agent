"""LLM provider utilities using a single OpenAI-compatible HTTP client path."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple
import time
import urllib.request

from sql_agent_demo.core.models import AgentConfig, LlmNotConfigured


def _resolve_api_key() -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise LlmNotConfigured("Set LLM_API_KEY to use the LLM provider.")
    return api_key


def _resolve_base_url() -> str | None:
    return os.environ.get("LLM_BASE_URL")


def _build_chat_model(model_name: str) -> Any:
    api_key = _resolve_api_key()
    base_url = _resolve_base_url() or "http://localhost:4141/v1"
    return SlimChatModel(model=model_name, api_key=api_key, base_url=base_url)


@dataclass
class ChatModelAdapter:
    """Adapter to normalize chat model interfaces."""

    client: Any
    last_metrics: Dict[str, Any] | None = None

    def _invoke(self, messages: Iterable[dict[str, str]]) -> tuple[Any, Dict[str, Any]]:
        start = time.perf_counter()
        response = self.client.generate(list(messages))
        duration_ms = (time.perf_counter() - start) * 1000
        metrics = self.client.last_metrics or {"duration_ms": duration_ms}
        self.last_metrics = metrics
        return response, metrics

    def generate(self, messages: Iterable[dict[str, str]]) -> str:
        response, _ = self._invoke(messages)
        if isinstance(response, str):
            return response
        if hasattr(response, "content"):
            return str(response.content)
        return str(response)

    def generate_json(self, messages: Iterable[dict[str, str]]) -> dict[str, Any]:
        """Generate a response and parse it into a JSON dict with light cleanup."""
        import json

        response, _ = self._invoke(messages)
        if isinstance(response, str):
            raw = response
        elif hasattr(response, "content"):
            raw = str(response.content)
        else:
            raw = str(response)
        text = raw.strip()

        if text.startswith("```") and text.endswith("```"):
            text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        if text.startswith("```json"):
            text = text[len("```json") :].strip().strip("`")

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass

        return {}


def build_llm_from_name(model_name: str) -> ChatModelAdapter:
    """Build a chat model adapter for the given model string."""
    client = _build_chat_model(model_name)
    return ChatModelAdapter(client)


def build_models(config: AgentConfig) -> Tuple[ChatModelAdapter, ChatModelAdapter]:
    """Build intent and SQL models based on configuration."""
    intent_model = build_llm_from_name(config.intent_model_name)
    sql_model = build_llm_from_name(config.sql_model_name)
    return intent_model, sql_model


# ---- Slim client (minimal HTTP payload to maximize gateway compatibility) ----


class SlimChatModel:
    """Minimal OpenAI-compatible chat client that sends only essential fields."""

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.last_metrics: Dict[str, Any] | None = None

    def _post(self, messages: Iterable[dict[str, str]], response_format: dict | None = None) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0,
        }
        if response_format:
            body["response_format"] = response_format

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            raw = resp.read().decode("utf-8")
        duration_ms = (time.perf_counter() - start) * 1000
        payload = json.loads(raw)
        usage = payload.get("usage", {})
        self.last_metrics = {
            "duration_ms": duration_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return payload

    def generate(self, messages: Iterable[dict[str, str]]) -> str:
        payload = self._post(messages)
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return str(message.get("content", "")).strip()

    def generate_json(self, messages: Iterable[dict[str, str]]) -> dict[str, Any]:
        payload = self._post(messages, response_format={"type": "json_object"})
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = str(message.get("content", "")).strip()
        try:
            return json.loads(text)
        except Exception:
            return {}


__all__ = ["ChatModelAdapter", "build_llm_from_name", "build_models"]
