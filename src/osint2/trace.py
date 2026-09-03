"""Append only trace.jsonl writer. One line per event, run_id stamped on every line.
Span names follow the GenAI semantic conventions used in the brief: invoke_agent, chat,
execute_tool."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TraceWriter:
    def __init__(self, path: Path, run_id: str):
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, span: str, **fields: Any) -> dict[str, Any]:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "span": span,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        return event


def read_trace(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def summarize_trace(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a trace up into the run stats the report carries (brief section 10)."""
    llm = [e for e in events if e.get("span") == "chat"]
    tools = [e for e in events if e.get("span") == "execute_tool"]
    tokens = {
        "input": sum(e.get("input_tokens") or 0 for e in llm),
        "output": sum(e.get("output_tokens") or 0 for e in llm),
        "reasoning": sum(e.get("reasoning_tokens") or 0 for e in llm),
        "cached_input": sum(e.get("cached_tokens") or 0 for e in llm),
    }
    cost = sum(e.get("cost_usd") or 0.0 for e in llm)
    llm_ms = sum(e.get("latency_ms") or 0 for e in llm)
    tool_ms = sum(e.get("latency_ms") or 0 for e in tools)
    return {
        "llm_calls": len(llm),
        "tool_calls": len(tools),
        "tool_errors": sum(1 for e in tools if e.get("error")),
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "llm_latency_ms": llm_ms,
        "tool_latency_ms": tool_ms,
    }
