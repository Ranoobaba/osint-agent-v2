"""OpenRouter chat wrapper, salvaged from v1 without the streaming path. Every call sends tools,
asks for usage accounting, enables reasoning, and writes one chat span to the trace with tokens,
reasoning tokens, cost, finish reason and latency. reasoning_details come back inside the
assistant message so the caller passes them back unmodified on the next turn."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import openai
from openai import AsyncOpenAI

from .config import Settings
from .trace import TraceWriter

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE = (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)


def _apply_cache_control(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic prompt-cache breakpoints via OpenRouter: the system prompt (stable anchor) and the
    last plain-text message (rolling breakpoint). Only for anthropic/* models."""
    out = [dict(m) for m in messages]
    for m in out:
        if m.get("role") == "system" and isinstance(m.get("content"), str) and m["content"]:
            m["content"] = [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]
            break
    for m in reversed(out):
        if isinstance(m.get("content"), str) and m["content"]:
            m["content"] = [{"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}]
            break
    return out


class ChatResult:
    def __init__(self, message: dict[str, Any], finish_reason: str, usage: dict[str, Any]):
        self.message = message
        self.finish_reason = finish_reason
        self.usage = usage

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return self.message.get("tool_calls") or []

    @property
    def text(self) -> str:
        content = self.message.get("content")
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return content or ""


class OpenRouterClient:
    def __init__(self, settings: Settings, trace: TraceWriter):
        self.settings = settings
        self.trace = trace
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key, base_url=OPENROUTER_BASE_URL,
            default_headers={"HTTP-Referer": settings.app_url, "X-Title": "osint-agent-v2"},
            timeout=120.0, max_retries=0,
        )

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, *,
        model: str | None = None, thread: str = "lead", step: int = 0,
        tool_choice: str | dict[str, Any] = "auto", response_format: dict[str, Any] | None = None,
        reasoning: bool = True, max_retries: int = 3,
    ) -> ChatResult:
        model = model or self.settings.lead_model
        if model.startswith("anthropic/"):
            messages = _apply_cache_control(messages)
        extra_body: dict[str, Any] = {"usage": {"include": True}}
        if reasoning:
            extra_body["reasoning"] = {"max_tokens": self.settings.reasoning_max_tokens}
        # OpenRouter checks affordability against max_tokens (default 65k for Opus). A modest cap keeps
        # a low balance from rejecting every call; a step never needs more than this.
        kwargs: dict[str, Any] = {"max_tokens": self.settings.max_output_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        if response_format:
            kwargs["response_format"] = response_format
            extra_body["provider"] = {"require_parameters": True}
        attempt = 0
        started = time.perf_counter()
        while True:
            try:
                response = await self.client.chat.completions.create(model=model, messages=messages, extra_body=extra_body, **kwargs)
                break
            except RETRYABLE as exc:
                attempt += 1
                if attempt > max_retries:
                    self.trace.write("chat", model=model, thread=thread, step=step,
                                     latency_ms=int((time.perf_counter() - started) * 1000),
                                     error=type(exc).__name__, error_message=str(exc)[:300], retry_count=attempt - 1)
                    raise
                await asyncio.sleep(min(2 ** attempt, 10))
            except openai.APIStatusError as exc:
                self.trace.write("chat", model=model, thread=thread, step=step,
                                 latency_ms=int((time.perf_counter() - started) * 1000),
                                 error=type(exc).__name__, error_message=str(exc)[:300], retry_count=attempt)
                raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        choice = response.choices[0]
        raw = choice.message.model_dump(exclude_none=True)
        message: dict[str, Any] = {"role": "assistant", "content": raw.get("content")}
        if raw.get("tool_calls"):
            message["tool_calls"] = raw["tool_calls"]
        if raw.get("reasoning_details"):
            message["reasoning_details"] = raw["reasoning_details"]
        usage = response.usage.model_dump() if response.usage else {}
        completion_details = usage.get("completion_tokens_details") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        usage_flat = {
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": completion_details.get("reasoning_tokens"),
            "cached_tokens": prompt_details.get("cached_tokens"), "cost_usd": usage.get("cost"),
        }
        self.trace.write("chat", model=getattr(response, "model", model), thread=thread, step=step, latency_ms=latency_ms,
                         finish_reason=choice.finish_reason, tool_calls=[tc["function"]["name"] for tc in message.get("tool_calls", [])],
                         retry_count=attempt, provider=getattr(response, "provider", None), response_id=response.id, **usage_flat)
        return ChatResult(message, choice.finish_reason or "", usage_flat)
