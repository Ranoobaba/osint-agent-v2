"""Tool registry. A data tool hits the network, is metered against the run budget, and has its
result stored as a source (with sha256) so claims can cite it. A bookkeeping tool only touches
run state and is never metered. run_tool() times the call, writes the execute_tool span, and turns
exceptions into text the model can act on."""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from ..budget import Budget
from ..config import BOOKKEEPING_TOOLS, Settings
from ..evidence import EvidenceStore
from ..trace import TraceWriter
from ..workspace import Workspace

MAX_TOOL_OUTPUT_CHARS = 12_000
TOOL_TIMEOUT_S = 60


@dataclass
class ToolResult:
    content: str
    error: Optional[str] = None
    url: Optional[str] = None            # the page or endpoint the content came from
    cost_usd: float = 0.0
    store_source: bool = True            # data tools store; bookkeeping tools do not
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    ws: Workspace
    trace: TraceWriter
    store: EvidenceStore
    budget: Budget
    settings: Settings
    state: dict[str, Any] = field(default_factory=dict)   # resolution, anchor, candidates, finish flag


ToolFn = Callable[..., Awaitable[ToolResult]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn
    requires: tuple[str, ...] = ()       # settings.tools entries that enable this tool

    def spec(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


def registry(settings: Settings) -> dict[str, Tool]:
    """Tools available for this configuration: every bookkeeping tool, plus the data tools whose
    requirement appears in settings.tools."""
    from .record_candidate import record_candidate
    from .record_claim import record_claim
    from .record_not_found import record_not_found
    from .finish import finish
    tools: list[Tool] = [record_candidate, record_claim, record_not_found, finish]
    if "github" in settings.tools:
        from .github_intel import github_intel
        tools.append(github_intel)
    if "gravatar" in settings.tools:
        from .gravatar import gravatar_lookup
        tools.append(gravatar_lookup)
    if "wayback" in settings.tools:
        from .wayback import wayback_lookup
        tools.append(wayback_lookup)
    if "whatsmyname" in settings.tools:
        from .whatsmyname import whatsmyname
        tools.append(whatsmyname)
    if "openalex" in settings.tools:
        from .openalex import openalex_lookup
        tools.append(openalex_lookup)
    if "perplexity" in settings.tools or "exa" in settings.tools:
        from .web_search import web_search
        tools.append(web_search)
    if "exa" in settings.tools:
        from .exa_contents import exa_contents
        tools.append(exa_contents)
    if "firecrawl" in settings.tools:
        from .fetch_page import fetch_page
        tools.append(fetch_page)
    return {t.name: t for t in tools}


def parse_tool_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return parsed if isinstance(parsed, dict) else {"_raw": raw}


def _memo_key(name: str, args: dict[str, Any]) -> Optional[str]:
    if name in BOOKKEEPING_TOOLS:
        return None
    try:
        if name in ("fetch_page", "exa_contents") and args.get("url"):
            return name + "|" + str(args["url"]).strip().rstrip("/").lower()
        return name + "|" + json.dumps(args, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        return None


async def run_tool(tools: dict[str, Tool], name: str, args: dict[str, Any], ctx: RunContext, *,
                   step: int, thread: str = "lead", tool_call_id: str | None = None) -> ToolResult:
    started = time.perf_counter()
    tool = tools.get(name)
    memo: dict[str, ToolResult] = ctx.state.setdefault("_memo", {})
    key = _memo_key(name, args)
    if key is not None and key in memo:
        cached = memo[key]
        ctx.trace.write("execute_tool", tool=name, args=args, thread=thread, step=step, tool_call_id=tool_call_id,
                        latency_ms=int((time.perf_counter() - started) * 1000), cached=True,
                        result_bytes=len(cached.content.encode("utf-8")), source_id=cached.meta.get("source_id"), error=cached.error)
        return cached

    ticket = None
    if tool is None:
        result = ToolResult(content=f"Unknown tool '{name}'. Available: {', '.join(tools)}.", error="UnknownTool", store_source=False)
    elif name not in BOOKKEEPING_TOOLS and (ticket := await ctx.budget.reserve(name)) is None:
        result = ToolResult(content=f"Skipped: run budget exhausted ({ctx.budget.exhausted()}). Record what you have and finish.",
                            error="BudgetExhausted", store_source=False)
    else:
        try:
            result = await asyncio.wait_for(tool.fn(ctx, **args), timeout=TOOL_TIMEOUT_S)
        except TypeError as exc:
            result = ToolResult(content=f"Bad arguments for {name}: {exc}", error="BadArguments", store_source=False)
        except asyncio.TimeoutError:
            result = ToolResult(content=f"{name} timed out after {TOOL_TIMEOUT_S}s. Try a narrower request.", error="Timeout", store_source=False)
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(content=f"{name} failed: {type(exc).__name__}: {str(exc)[:300]}", error=type(exc).__name__, store_source=False)
        if ticket is not None:
            await ctx.budget.settle(ticket, result.cost_usd)
            tc = ctx.state.setdefault("thread_calls", {})
            tc[thread] = tc.get(thread, 0) + 1

    if len(result.content) > MAX_TOOL_OUTPUT_CHARS:
        result.content = result.content[:MAX_TOOL_OUTPUT_CHARS] + f"\n\n[truncated to {MAX_TOOL_OUTPUT_CHARS} chars]"

    source_id = None
    if result.store_source and result.error is None and name not in BOOKKEEPING_TOOLS and result.content.strip():
        src = ctx.store.add_source(name, args, result.content, result.url, step)
        source_id = src.id
        result.meta["source_id"] = source_id
        result.content = f"[source_id: {source_id}]  cite this id in record_claim\n" + result.content

    ctx.trace.write("execute_tool", tool=name, args=args, thread=thread, step=step, tool_call_id=tool_call_id,
                    latency_ms=int((time.perf_counter() - started) * 1000), result_bytes=len(result.content.encode("utf-8")),
                    source_id=source_id, source_path=(ctx.store.sources[source_id].path if source_id else None),
                    content_hash=(ctx.store.sources[source_id].content_hash if source_id else None),
                    error=result.error, cost_usd=result.cost_usd, budget=ctx.budget.snapshot(),
                    **{k: v for k, v in result.meta.items() if k != "source_id"})
    if key is not None and result.error is None:
        memo[key] = result
    ents = ctx.state.get("entities")
    if ents is not None and name not in BOOKKEEPING_TOOLS:
        try:
            ents.mark_explored(url=args.get("url"), handle=args.get("username"), email=args.get("email"),
                               name=args.get("name") or (args.get("query") if name in ("web_search", "openalex_lookup") else None),
                               domain=(args.get("url") or "").split("/")[0] if name == "wayback_lookup" else None)
            ents.persist()
        except Exception:  # noqa: BLE001
            pass
    return result
