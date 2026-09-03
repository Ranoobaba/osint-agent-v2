"""record_candidate: the model reports every plausible profile it sees; code merges it into the
candidate list, scores it against the anchor, rewrites the resolution and tells the model the score,
the status and what evidence would raise it. Salvaged from v1; identity never depends on the model's
opinion of who the person is."""
from __future__ import annotations

import re
from typing import Any

from ..resolution import (Anchor, Candidate, Employment, Evidence, missing_evidence_hint, norm_email, norm_handle,
                          norm_url, resolve)
from . import RunContext, Tool, ToolResult


def _keys(c: Candidate) -> set[str]:
    return ({"email:" + norm_email(e) for e in c.emails}
            | {"url:" + norm_url(u) for u in c.profile_urls}
            | {"handle:" + norm_handle(h) for h in c.handles}
            | ({"avatar:" + c.avatar_hash} if c.avatar_hash else set()))


def _merge(into: Candidate, new: Candidate) -> Candidate:
    def uniq(a: list, b: list, key=lambda x: x) -> list:
        seen, out = set(), []
        for x in a + b:
            k = key(x)
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out
    into.names = uniq(into.names, new.names, str.lower)
    into.emails = uniq(into.emails, new.emails, norm_email)
    into.handles = uniq(into.handles, new.handles, norm_handle)
    into.profile_urls = uniq(into.profile_urls, new.profile_urls, norm_url)
    into.avatar_hash = into.avatar_hash or new.avatar_hash
    into.employers = uniq(into.employers, new.employers, lambda e: (e.name.lower(), (e.role or "").lower()))
    into.education = uniq(into.education, new.education, lambda e: (e.name.lower(), (e.role or "").lower()))
    into.locations = uniq(into.locations, new.locations, str.lower)
    into.bio = into.bio or new.bio
    into.disclaims_identity = into.disclaims_identity or new.disclaims_identity
    into.evidence = uniq(into.evidence, new.evidence, lambda e: (e.claim.lower(), e.source_url))
    return into


def load_candidates(ctx: RunContext) -> list[Candidate]:
    return list(ctx.state.setdefault("candidates", []))


async def _record_candidate(
    ctx: RunContext, label: str, evidence: list[dict[str, Any]],
    names: list[str] | None = None, emails: list[str] | None = None, handles: list[str] | None = None,
    profile_urls: list[str] | None = None, avatar_hash: str | None = None,
    employers: list[dict[str, Any]] | None = None, education: list[dict[str, Any]] | None = None,
    locations: list[str] | None = None, bio: str | None = None, disclaims_identity: bool = False,
) -> ToolResult:
    names = [n.strip() for n in (names or []) if n and n.strip()]
    if not names:
        head = re.split(r"\s+[-|(]\s*|,\s", label.strip(), maxsplit=1)[0].strip()
        if head and len(head.split()) <= 5 and "@" not in head:
            names = [head]
    anchor: Anchor = ctx.state["anchor"]
    cands = load_candidates(ctx)
    new = Candidate(
        id="tmp", label=label.strip(), names=names or [], emails=emails or [], handles=handles or [],
        profile_urls=profile_urls or [], avatar_hash=avatar_hash,
        employers=[Employment(**{k: v for k, v in e.items() if k in Employment.model_fields}) for e in (employers or []) if e.get("name")],
        education=[Employment(**{k: v for k, v in e.items() if k in Employment.model_fields}) for e in (education or []) if e.get("name")],
        locations=locations or [], bio=bio, disclaims_identity=disclaims_identity,
        evidence=[Evidence(**{k: v for k, v in e.items() if k in Evidence.model_fields}) for e in evidence if e.get("claim") and e.get("source_url")],
        first_seen_step=ctx.state.get("step", 0),
    )
    if not new.evidence:
        return ToolResult(content="record_candidate needs at least one evidence item with claim and source_url.", error="BadArguments", store_source=False)

    target = None
    nk = _keys(new)
    for c in cands:
        if nk & _keys(c):
            target = c
            break
    if target is None:
        new.id = f"cand{len(cands) + 1}"
        cands.append(new)
        target = new
        action = "created"
    else:
        _merge(target, new)
        action = "merged into"
    ctx.state["candidates"] = cands
    ctx.ws.write_json("candidates.json", [c.model_dump() for c in cands])

    res = resolve(anchor, cands)
    ctx.state["resolution"] = res
    ctx.ws.write_json("resolution.json", res.model_dump())
    mine = next(b for b in res.breakdowns if b.candidate_id == target.id)
    ctx.trace.write("resolution", step=ctx.state.get("step", 0), status=res.status, best=res.best_candidate_id,
                    score=res.score, markers=res.matched_markers, candidates=len(cands),
                    changed=target.id, changed_score=mine.score, vetoed=bool(mine.contradictions))
    ctx.state["step_candidates"] = ctx.state.get("step_candidates", 0) + (1 if action == "created" else 0)

    lines = [f"# record_candidate: {action} {target.id} ({target.label})",
             f"score: {mine.score:.2f}  markers: {mine.matched_markers or '[]'}  fields: "
             + ", ".join(f"{k}={v:.2f}" for k, v in mine.fields.items())]
    if mine.contradictions:
        lines.append("VETO: " + "; ".join(mine.contradictions))
    if mine.gated:
        lines.append(f"gated: {mine.reason}")
    if mine.capped:
        lines.append("capped at 0.60: only one field was comparable; a single match is never enough")
    lines.append("hint: " + missing_evidence_hint(anchor, mine))
    lines.append("")
    lines.append(f"identity status now: {res.status.upper()}  best={res.best_candidate_id} score={res.score:.2f}"
                 + (f"  runner_up={res.runner_up['id']} score={res.runner_up['score']:.2f}" if res.runner_up else ""))
    if res.status != "resolved":
        lines.append("Not resolved. Findings you record now must carry candidate_id; they are attributed only if that candidate wins. "
                     "Find a hard key (email, handle, profile URL, avatar) or a second independent domain confirming employer and location.")
    else:
        lines.append(f"Resolved. New findings default to candidate_id={res.best_candidate_id}. Keep recording other profiles you meet so they are listed as rejected.")
    return ToolResult(content="\n".join(lines), store_source=False,
                      meta={"candidate_id": target.id, "action": action, "score": mine.score, "status": res.status,
                            "markers": len(mine.matched_markers), "vetoed": bool(mine.contradictions), "candidates": len(cands)})


record_candidate = Tool(
    name="record_candidate",
    description=(
        "Report a possible match for the target: a profile page, a bio, a GitHub account, a Gravatar profile. Call it for "
        "EVERY plausible person you encounter, including ones you suspect are the wrong person; the scorer decides, not you. "
        "Pass only what the page states, each evidence claim with the URL you read it on. Returns the candidate's score, the "
        "identity status (resolved / ambiguous / unresolved) and what evidence would raise the score."
    ),
    parameters={
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Short human label, e.g. 'Jane Doe, GitHub jdoe'."},
            "names": {"type": "array", "items": {"type": "string"}, "description": "The person's name as the page writes it, plus variants."},
            "emails": {"type": "array", "items": {"type": "string"}},
            "handles": {"type": "array", "items": {"type": "string"}},
            "profile_urls": {"type": "array", "items": {"type": "string"}},
            "avatar_hash": {"type": "string", "description": "sha256 from gravatar_lookup, if any."},
            "employers": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "role": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
                "required": ["name"]}},
            "education": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "role": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
                "required": ["name"]}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "bio": {"type": "string"},
            "disclaims_identity": {"type": "boolean", "description": "True if the page explicitly says this is NOT the target."},
            "evidence": {"type": "array", "items": {"type": "object", "properties": {
                "claim": {"type": "string"}, "source_url": {"type": "string"}}, "required": ["claim", "source_url"]}},
        },
        "required": ["label", "names", "evidence"],
    },
    fn=_record_candidate,
)
