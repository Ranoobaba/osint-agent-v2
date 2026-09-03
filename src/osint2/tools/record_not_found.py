"""record_not_found: a thin alias for record_claim with kind not_found, so the model has an obvious
door for honesty."""
from __future__ import annotations

from . import RunContext, Tool, ToolResult
from .record_claim import _record_claim


async def _record_not_found(ctx: RunContext, field: str, searched: list[str], note: str | None = None) -> ToolResult:
    return await _record_claim(ctx, [{"kind": "not_found", "field": field, "value": note or "", "searched": searched}])


record_not_found = Tool(
    name="record_not_found",
    description=("Record a field you looked for and could not establish from any source in this run. Name the source ids "
                 "or tools you tried. A wrong claim costs more than a missing one; use this instead of guessing."),
    parameters={"type": "object", "properties": {
        "field": {"type": "string"},
        "searched": {"type": "array", "items": {"type": "string"}, "description": "source ids or tool names tried"},
        "note": {"type": "string", "description": "optional: what would settle it"},
    }, "required": ["field", "searched"]},
    fn=_record_not_found,
)
