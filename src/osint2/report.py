"""The report is a pure function of what is on disk: the admitted claims, the candidates, and the
resolution. The model never writes it. Confidence is computed here at emission time, from the
number of independent source domains behind a field/value and the final resolution score."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Optional
from urllib.parse import urlparse

from .evidence import Claim, EvidenceStore, norm_text
from .graph import build_graph
from .resolution import Anchor, Candidate, Resolution, missing_evidence_hint


def _norm_fact(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated findings. Two findings are the same when they share a normalized value, or
    share a field with one value contained in the other. The richer text wins, the highest confidence
    wins, distinct source URLs are kept on the survivor. Salvaged from v1."""
    kept: list[dict[str, Any]] = []
    for f in findings:
        val = _norm_fact(f.get("value"))
        if not val:
            continue
        fld = _norm_fact(f.get("field"))
        dup = None
        for k in kept:
            kval = _norm_fact(k.get("value"))
            if val == kval or (bool(fld) and fld == _norm_fact(k.get("field")) and (val in kval or kval in val)):
                dup = k
                break
        if dup is None:
            kept.append(dict(f))
            continue
        if len(val) > len(_norm_fact(dup.get("value"))):
            dup["value"] = f.get("value")
        try:
            if float(f.get("confidence") or 0) > float(dup.get("confidence") or 0):
                dup["confidence"] = f.get("confidence")
        except (TypeError, ValueError):
            pass
        src, dsrc = f.get("source_url"), dup.get("source_url")
        if src and src != dsrc:
            extra = dup.setdefault("also_sourced_from", [])
            if src not in extra:
                extra.append(src)
        for extra_id in [f.get("id")] + list(f.get("also_claim_ids") or []):
            if extra_id and extra_id != dup.get("id"):
                dup.setdefault("also_claim_ids", []).append(extra_id)
        if f.get("sensitive"):
            dup["sensitive"] = True
    return kept


def _domain(url: Optional[str]) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url if "://" in url else "https://" + url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _confidence(findings: list[Claim], resolution_score: float, attributed: bool) -> dict[str, float]:
    """0.7 with one source domain for a field/value, 0.9 with two independent domains, times the
    resolution score when attributed."""
    domains: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in findings:
        domains[(norm_text(c.field), norm_text(c.value))].add(_domain(c.source_url) or c.source_id or "")
    out = {}
    for c in findings:
        n = len(domains[(norm_text(c.field), norm_text(c.value))])
        base = 0.9 if n >= 2 else 0.7
        out[c.id] = round(base * (resolution_score if attributed else 1.0), 2)
    return out


def _finding_dict(c: Claim, conf: float) -> dict[str, Any]:
    return {"id": c.id, "category": c.category, "field": c.field, "value": c.value, "confidence": conf,
            "sensitive": c.sensitive, "source_url": c.source_url, "source_id": c.source_id, "excerpt": c.excerpt,
            "content_hash": c.content_hash, "method": c.method, "candidate_id": c.candidate_id, "step": c.step}


def build_report(anchor: Anchor, resolution: Resolution, candidates: list[Candidate], store: EvidenceStore,
                 run: dict[str, Any], same_person_ids: set[str] | None = None) -> dict[str, Any]:
    same = set(same_person_ids or set())
    if resolution.status == "resolved" and resolution.best_candidate_id:
        same.add(resolution.best_candidate_id)
    by_id = {c.id: c for c in candidates}
    best = by_id.get(resolution.best_candidate_id) if resolution.best_candidate_id else None

    all_findings = store.findings()
    if resolution.status == "resolved":
        attributed = [c for c in all_findings if c.candidate_id in same]
        excluded = [c for c in all_findings if c.candidate_id not in same]
    else:
        attributed, excluded = [], list(all_findings)
    conf_attr = _confidence(attributed, resolution.score, True)
    conf_excl = _confidence(excluded, resolution.score, False)
    findings = dedupe_findings([_finding_dict(c, conf_attr[c.id]) for c in attributed])
    excluded_findings = []
    for c in excluded:
        d = _finding_dict(c, conf_excl[c.id])
        d["excluded_reason"] = ("identity not resolved" if resolution.status != "resolved"
                                else f"attributed to {c.candidate_id or 'no candidate'}, not the resolved person")
        excluded_findings.append(d)

    admitted_ids = {c.id for c in attributed}
    synthesis = [{"id": c.id, "claim": c.value, "based_on": c.based_on, "confidence": round(min(conf_attr.get(b, 0.7) for b in c.based_on), 2)}
                 for c in store.claims if c.kind == "synthesis" and all(b in admitted_ids for b in c.based_on)]
    conflicts = [{"id": c.id, "field": c.field, "values": c.value.split(" | "), "based_on": c.based_on}
                 for c in store.claims if c.kind == "conflict"]
    not_found = [{"field": c.field, "note": c.value or None, "searched": c.searched} for c in store.claims if c.kind == "not_found"]
    if resolution.status != "resolved":
        # Say what would have settled identity, so an honest non-answer is still actionable.
        top = max(resolution.breakdowns, key=lambda b: b.score, default=None)
        hint = missing_evidence_hint(anchor, top) if top else "no candidate matched the anchor; a hard key (email, handle, profile URL) would settle it"
        not_found.insert(0, {"field": "identity", "note": f"{resolution.status}: {hint}", "searched": [s.tool for s in store.sources.values()][:8]})

    cand_rows = []
    for b in resolution.breakdowns:
        c = by_id.get(b.candidate_id)
        if not c:
            continue
        cand_rows.append({"id": c.id, "label": c.label, "names": c.names, "score": round(b.score, 3), "markers": b.matched_markers,
                          "status": "resolved" if c.id in same else "rejected",
                          "reason": ("; ".join(b.contradictions) if b.contradictions else (b.reason or ("winner" if c.id in same else "lower score"))),
                          "profile_urls": c.profile_urls, "handles": c.handles})

    identity = {
        "status": resolution.status, "name": (best.names[0] if best and best.names else (best.label if best else None)),
        "candidate_id": resolution.best_candidate_id, "score": round(resolution.score, 3),
        "markers": resolution.matched_markers, "runner_up": resolution.runner_up,
        "judge": resolution.judge.model_dump() if resolution.judge else None,
        "candidates": cand_rows,
        "summary": (f"Resolved to {best.label} with markers {resolution.matched_markers}" if resolution.status == "resolved" and best
                    else f"Identity {resolution.status}: {len(candidates)} candidate(s) considered, none met the bar"),
    }
    graph = build_graph(anchor, resolution, candidates, findings, [dict(s, claim=s["claim"]) for s in synthesis], same)
    return {
        "target": anchor.raw, "anchor": anchor.model_dump(), "identity": identity,
        "findings": findings, "excluded_findings": excluded_findings, "not_found": not_found,
        "conflicts": conflicts, "synthesis": synthesis,
        "sources": [{"id": s.id, "tool": s.tool, "url": s.url, "path": s.path, "content_hash": s.content_hash} for s in store.sources.values()],
        "graph": graph, "run": run,
    }
