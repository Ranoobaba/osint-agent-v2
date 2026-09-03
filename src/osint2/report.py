"""The report is a pure function of what is on disk: the evidence graph, the admitted claims, and
the resolution. The model never writes it. Stage 0 carries only the finding dedupe salvaged from
v1; build_report arrives in Stage 1 and grows in Stage 2."""
from __future__ import annotations

import re
from typing import Any


def _norm_fact(s: Any) -> str:
    """Normalize a finding value for duplicate detection: lowercase, strip punctuation and spacing."""
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse repeated findings. Two findings are the same when they share a normalized value, or
    share a field with one value contained in the other (a shorter restatement). The richer text wins,
    the highest confidence wins, and distinct source URLs are kept on the survivor so no provenance is
    lost. Salvaged from v1 agent.py."""
    kept: list[dict[str, Any]] = []
    for f in findings:
        val = _norm_fact(f.get("value"))
        if not val:
            continue
        fld = _norm_fact(f.get("field"))
        dup = None
        for k in kept:
            kval = _norm_fact(k.get("value"))
            same_val = val == kval
            same_field_nested = bool(fld) and fld == _norm_fact(k.get("field")) and (val in kval or kval in val)
            if same_val or same_field_nested:
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
        if f.get("sensitive"):
            dup["sensitive"] = True
    return kept
