"""Per-source extractor (EXTRACTOR=1). After identity is RESOLVED, every new source a data tool stores
is handed to a cheap model with structured output that proposes claims with verbatim quotes. The
proposals go through the same EvidenceStore.admit gate as the lead's own claims and are pinned to the
resolved candidate; the lead never has to spend a turn extracting from a page it already fetched.
Off before resolution: a claim needs a candidate, and binding pages to candidates is the lead's job.
Measured offline on saved sources (autoresearch/LEARNINGS.md): +0.12 recall on michael_jordan at $0.02
per source with Sonnet; Haiku and a 6k-character cap are the shipped defaults for cost."""
from __future__ import annotations

import json
from typing import Any

from .llm import OpenRouterClient
from .tools import RunContext

# Only page-like sources are worth an extractor pass. Tool renderings (GitHub API, Gravatar, whatsmyname,
# OpenAlex, holehe, Roblox) are already structured and the lead records what matters from them; running
# the extractor over them produced run metadata as findings ("repos_scanned = 5").
PAGE_TOOLS = {"exa_contents", "fetch_page", "wayback_lookup", "web_search", "people_search", "tinder_check"}

PROMPT = """You extract facts about ONE person from ONE page. Return only a JSON object {"claims": [...]}.
Each claim: {"field": snake_case, "value": the fact as stated, "excerpt": the exact line from the page that states it,
"category": one of identity, contact, professional, education, online_presence, projects, connections, personal, sensitive, other}.
Rules: only facts the page states about the named person; one value per claim; the excerpt is copied verbatim and contains
the value; a relationship to another person gets a field starting with connection_ or collaborator; skip navigation,
boilerplate, and anything inferred rather than read. At most 20 claims."""

SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "items": {"type": "object", "properties": {
    "field": {"type": "string"}, "value": {"type": "string"}, "excerpt": {"type": "string"}, "category": {"type": "string"}},
    "required": ["field", "value", "excerpt", "category"], "additionalProperties": False}}}, "required": ["claims"], "additionalProperties": False}


async def extract_source(ctx: RunContext, llm: OpenRouterClient, source_id: str, step: int) -> dict[str, Any]:
    res = ctx.state.get("resolution")
    if res is None or res.status != "resolved":
        return {"skipped": "not resolved"}
    src = ctx.store.sources.get(source_id)
    if src is None or src.tool not in PAGE_TOOLS:
        return {"skipped": "not a page source"}
    cands = ctx.state.get("candidates", [])
    person = next((c for c in cands if c.id == res.best_candidate_id), None)
    who = f"{person.label} (names {person.names}, handles {person.handles}, emails {person.emails})" if person else ctx.state["anchor"].raw
    text = ctx.store.source_text(source_id)[: ctx.settings.extractor_chars]
    try:
        r = await llm.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": f"Person: {who}\n\nPage (source {source_id}):\n{text}"}],
                           tools=None, model=ctx.settings.extractor_model, thread="extractor", step=step, reasoning=False,
                           response_format={"type": "json_schema", "json_schema": {"name": "claims", "strict": True, "schema": SCHEMA}})
    except Exception as exc:  # noqa: BLE001
        ctx.trace.write("extractor", step=step, source_id=source_id, error=f"{type(exc).__name__}: {str(exc)[:160]}")
        return {"error": type(exc).__name__}
    await ctx.budget.charge_llm(r.usage.get("cost_usd"))
    try:
        claims = json.loads(r.text).get("claims", [])
    except ValueError:
        return {"error": "bad json"}
    admitted = rejected = 0
    for c in claims[:20]:
        if not isinstance(c, dict):
            continue
        claim, reason = ctx.store.admit({**c, "source_id": source_id, "candidate_id": res.best_candidate_id}, step=step, thread="extractor",
                                        default_candidate=res.best_candidate_id)
        if claim:
            admitted += 1
            ents = ctx.state.get("entities")
            if ents is not None:
                try:
                    ents.ingest_claim(claim, res.best_candidate_id)
                except Exception:  # noqa: BLE001
                    pass
            ctx.trace.write("claim_admitted", step=step, claim_id=claim.id, kind=claim.kind, field=claim.field, value=claim.value[:200],
                            source_id=claim.source_id, content_hash=claim.content_hash, method=claim.method, candidate_id=claim.candidate_id,
                            excerpt=(claim.excerpt or "")[:300], by="extractor")
        else:
            rejected += 1
            ctx.trace.write("claim_rejected", step=step, kind="finding", field=c.get("field"), value=str(c.get("value"))[:200], reason=reason, by="extractor")
    ctx.state["step_admitted"] = ctx.state.get("step_admitted", 0) + admitted
    ctx.trace.write("extractor", step=step, source_id=source_id, proposed=len(claims), admitted=admitted, rejected=rejected, cost_usd=r.usage.get("cost_usd"))
    return {"admitted": admitted, "rejected": rejected}
