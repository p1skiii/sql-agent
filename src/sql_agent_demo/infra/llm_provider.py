"""Minimal OpenAI-compatible LLM provider for AMP runtime."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from sql_agent_demo.core.models import AgentConfig


class ModelConfigError(RuntimeError):
    pass


def _resolve_api_key() -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise ModelConfigError("Set LLM_API_KEY to enable model-backed planning.")
    return api_key


def _resolve_base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "http://localhost:4141/v1")


@dataclass
class ChatModelAdapter:
    client: Any
    last_metrics: dict[str, Any] | None = None

    def _invoke(self, messages: Iterable[dict[str, str]], response_format: dict[str, Any] | None = None) -> str:
        text, metrics = self.client.generate(messages, response_format=response_format)
        self.last_metrics = metrics
        return text

    def generate(self, messages: Iterable[dict[str, str]]) -> str:
        return self._invoke(messages)

    def generate_json(self, messages: Iterable[dict[str, str]]) -> dict[str, Any]:
        text = self._invoke(messages, response_format={"type": "json_object"}).strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except Exception:
                    return {}
        return {}


class SlimChatModel:
    def __init__(self, *, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _post(self, messages: Iterable[dict[str, str]], response_format: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0,
        }
        if response_format is not None:
            body["response_format"] = response_format

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=data)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        start = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
        duration_ms = (time.perf_counter() - start) * 1000

        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = str(message.get("content", "")).strip()
        usage = payload.get("usage", {})
        metrics = {
            "duration_ms": duration_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
        return text, metrics

    def generate(self, messages: Iterable[dict[str, str]], response_format: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
        return self._post(messages, response_format=response_format)


def build_llm_from_name(model_name: str) -> ChatModelAdapter:
    api_key = _resolve_api_key()
    base_url = _resolve_base_url()
    return ChatModelAdapter(SlimChatModel(model=model_name, api_key=api_key, base_url=base_url))


def build_models(config: AgentConfig) -> tuple[ChatModelAdapter, ChatModelAdapter]:
    return build_llm_from_name(config.intent_model_name), build_llm_from_name(config.sql_model_name)


def build_models_optional(config: AgentConfig) -> tuple[ChatModelAdapter | None, ChatModelAdapter | None]:
    try:
        return build_models(config)
    except Exception:
        return None, None


__all__ = ["ChatModelAdapter", "ModelConfigError", "build_llm_from_name", "build_models", "build_models_optional"]
