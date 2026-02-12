"""LLM provider utilities using ChatOpenAI with optional base_url."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple
import time

from sql_agent_demo.core.models import AgentConfig, LlmNotConfigured


def _resolve_api_key() -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise LlmNotConfigured("Set LLM_API_KEY to use the LLM provider.")
    return api_key


def _resolve_base_url() -> str | None:
    return os.environ.get("LLM_BASE_URL")


def _build_chat_model(model_name: str) -> Any:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise LlmNotConfigured("langchain-openai is required. Install with the 'openai' extra.") from exc

    api_key = _resolve_api_key()
    base_url = _resolve_base_url()

    kwargs = {"model": model_name, "api_key": api_key, "temperature": 0}
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)


@dataclass
class ChatModelAdapter:
    """Adapter to normalize chat model interfaces."""

    client: Any
    last_metrics: Dict[str, Any] | None = None

    def _extract_usage(self, response: Any, duration_ms: float) -> Dict[str, Any]:
        usage = None
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage") or response.response_metadata.get("usage")
        if usage is None and hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
        usage = usage or {}

        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens") or usage.get("total")

        return {
            "duration_ms": duration_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _invoke(self, messages: Iterable[dict[str, str]]) -> tuple[Any, Dict[str, Any]]:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
        except ImportError as exc:
            raise LlmNotConfigured("langchain-core is required for chat message conversion.") from exc

        def _to_message(msg: dict[str, str]):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                return SystemMessage(content=content)
            if role == "assistant":
                return AIMessage(content=content)
            return HumanMessage(content=content)

        lc_messages = [_to_message(m) for m in messages]

        start = time.perf_counter()
        response = self.client.invoke(lc_messages)
        duration_ms = (time.perf_counter() - start) * 1000
        metrics = self._extract_usage(response, duration_ms)
        self.last_metrics = metrics
        return response, metrics

    def generate(self, messages: Iterable[dict[str, str]]) -> str:
        response, _ = self._invoke(messages)
        if hasattr(response, "content"):
            return str(response.content)
        return str(response)

    def generate_json(self, messages: Iterable[dict[str, str]]) -> dict[str, Any]:
        """Generate a response and parse it into a JSON dict with light cleanup."""
        import json

        response, _ = self._invoke(messages)
        if hasattr(response, "content"):
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


__all__ = ["ChatModelAdapter", "build_llm_from_name", "build_models"]
