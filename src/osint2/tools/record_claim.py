"""record_claim: the model proposes findings, not_found entries, conflicts and syntheses. Code admits
or rejects each one (see evidence.py). The model never writes the report; this is the only door
a fact can enter through."""
from __future__ import annotations

from typing import Any

from . import RunContext, Tool, ToolResult

CATEGORIES = ["identity", "contact", "professional", "education", "online_presence", "projects",
              "connections", "personal", "sensitive", "other"]


async def _record_claim(ctx: RunContext, claims: list[dict[str, Any]]) -> ToolResult:
    if not isinstance(claims, list) or not claims:
        return ToolResult(content="record_claim needs a non-empty claims list.", error="BadArguments", store_source=False)
    res = ctx.state.get("resolution")
    default_candidate = res.best_candidate_id if (res is not None and res.status == "resolved") else None
    pin = ctx.state.get("pin_candidate")   # set while a deep-dive subagent runs: its claims are about the resolved person
    lines, admitted, rejected = [], 0, 0
    for p in claims[:10]:
        if not isinstance(p, dict):
            continue
        ctx.trace.write("claim_proposed", step=ctx.state.get("step", 0), kind=p.get("kind", "finding"),
                        field=p.get("field"), value=str(p.get("value"))[:200], source_id=p.get("source_id"))
        if pin:
            p = {**p, "candidate_id": pin}
        claim, reason = ctx.store.admit(p, step=ctx.state.get("step", 0), default_candidate=default_candidate,
                                        thread=("subagent" if pin else "lead"))
        if claim:
            admitted += 1
            ctx.trace.write("claim_admitted", step=ctx.state.get("step", 0), claim_id=claim.id, kind=claim.kind,
                            field=claim.field, value=claim.value[:200], source_id=claim.source_id,
                            content_hash=claim.content_hash, method=claim.method, candidate_id=claim.candidate_id,
                            excerpt=(claim.excerpt or "")[:300])
            lines.append(f"ADMITTED {claim.id} {claim.kind} {claim.field}={claim.value[:80]!r}"
                         + (f" candidate={claim.candidate_id}" if claim.candidate_id else " (no candidate: will be excluded unless identity resolves)"))
        else:
            rejected += 1
            ctx.trace.write("claim_rejected", step=ctx.state.get("step", 0), kind=p.get("kind", "finding"),
                            field=p.get("field"), value=str(p.get("value"))[:200], reason=reason)
            lines.append(f"REJECTED {p.get('field')}={str(p.get('value'))[:60]!r}: {reason}")
    if len(claims) > 10:
        lines.append(f"({len(claims) - 10} claims beyond the batch limit of 10 were ignored; call again)")
    ctx.state["step_admitted"] = ctx.state.get("step_admitted", 0) + admitted
    return ToolResult(content="\n".join(lines), store_source=False, meta={"admitted": admitted, "rejected": rejected})


record_claim = Tool(
    name="record_claim",
    description=(
        "Record what you learned. Every finding must cite the source_id of a tool result from THIS run and quote "
        "the exact line (excerpt) from it that states the value; the value string must appear inside the excerpt. "
        "One value per claim: record each repo, each account, each employer as its own claim, never a comma list. "
        "Code checks the quote against the stored page; a quote that is not in the page, or that does not contain "
        "the value, is rejected with the line you should have quoted. Findings recorded before "
        "identity is resolved must name the candidate_id they are about. Use kind 'not_found' for a field you searched "
        "for and could not establish (name the source ids or tools you tried in searched), 'conflict' when two admitted "
        "findings disagree (based_on = their claim ids), and 'synthesis' for an inference resting on two or more "
        "admitted findings (based_on = their ids). Up to 10 claims per call."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claims": {"type": "array", "items": {"type": "object", "properties": {
                "kind": {"type": "string", "enum": ["finding", "not_found", "conflict", "synthesis"]},
                "field": {"type": "string", "description": "snake_case, e.g. current_employer, current_title, education, github_handle, personal_email, location_city, project, publication"},
                "value": {"type": "string"},
                "category": {"type": "string", "enum": CATEGORIES},
                "source_id": {"type": "string", "description": "e.g. s003, from a tool result in this run"},
                "excerpt": {"type": "string", "description": "the exact sentence or line from that source that states the value"},
                "candidate_id": {"type": "string", "description": "which candidate this fact is about (from record_candidate)"},
                "sensitive": {"type": "boolean"},
                "based_on": {"type": "array", "items": {"type": "string"}, "description": "claim ids, for conflict and synthesis"},
                "searched": {"type": "array", "items": {"type": "string"}, "description": "source ids or tool names tried, for not_found"},
            }, "required": ["field"]}},
        },
        "required": ["claims"],
    },
    fn=_record_claim,
)
