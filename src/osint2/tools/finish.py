"""finish: the model says it is done. The loop decides whether to accept (it always does once the
model asks; saturation and budget stop the loop without the model asking). No findings are read
from this call; the report is built from the store."""
from __future__ import annotations

from . import RunContext, Tool, ToolResult


async def _finish(ctx: RunContext, reason: str = "") -> ToolResult:
    ctx.state["finish"] = True
    ctx.state["finish_reason"] = reason[:300]
    return ToolResult(content="Finishing. The report is built from the recorded claims.", store_source=False)


finish = Tool(
    name="finish",
    description="Call when every useful lead is exhausted or nothing new is turning up. Say why in one sentence.",
    parameters={"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]},
    fn=_finish,
)
