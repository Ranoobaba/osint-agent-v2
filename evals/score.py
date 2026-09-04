"""Score one run's report against one golden entry.

    uv run python evals/score.py <golden.jsonl> <golden_id> <report.json> [workspace_dir]

The number this produces is the ladder's currency, so the rules are spelled out here and nowhere
else. See the plan file for the reasoning behind each rule.

Vocabulary
  admitted    every finding that passed claim admission (report.findings plus
              report.excluded_findings; the scorer reads both)
  attributed  admitted findings whose candidate_id is the resolved candidate (empty unless the
              identity status is resolved)
  recall(F)   weighted share of auto-scorable golden facts whose value appears in the findings F
  wrong(F)    summed penalty over findings in F: golden weight for a contradiction on a known
              field, 3 for a decoy leak, 2 for a provenance failure
  net         the per-target score in [0, 1]

Identity branches
  golden expects resolved:
    resolved to a name not in name_any            -> 0
    resolved to the right name                    -> max(0, recall(attributed) - wrong(attributed))
    ambiguous or unresolved                       -> 0.5 * max(0, recall(admitted) - wrong(admitted))
  golden expects ambiguous (collision, no key):
    base 1.0 if status is ambiguous and every expected name matches a candidate label, else 0;
    minus 0.5 per decoy leak in admitted findings; floored at 0
  golden expects unresolved (invented person):
    0 if resolved; else 1 - wrong_count(admitted) / max(1, len(admitted))

Provenance is judged against the stored excerpt and content hash written at admission time. A
finding with no excerpt field at all (a v1 report) is scored with the provenance term skipped and
`prov_checked` false, so the Stage 0 calibration compares like with like.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

DECOY_PENALTY = 3.0
# Only single-valued fields can be contradicted. A person has many projects, accounts, employers over
# time and emails; an extra value there is not a contradiction. These are the fields where a value
# that matches none of the golden values is wrong.
EXCLUSIVE_FIELDS = {"current_employer", "current_title", "current_role", "location_city", "location", "age",
                    "birth_year", "birth_date", "religion", "partner", "spouse", "nationality", "phone",
                    "github_handle", "linkedin_url", "google_scholar_url", "personal_website"}
PROVENANCE_PENALTY = 2.0
AMBIGUOUS_LEAK_PENALTY = 0.5
NOT_RESOLVED_FACTOR = 0.5
MARKDOWN_CHARS = "*_#`>|"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.translate({ord(c): " " for c in MARKDOWN_CHARS})
    return " ".join(text.casefold().split())


def match(needle: str, hay: str) -> bool:
    """v1 rule, unchanged: substring first; emails and urls substring only; else two fuzzy gates."""
    n, h = normalize(needle), normalize(hay)
    if not n or not h:
        return False
    if n in h:
        return True
    if "@" in n or "/" in n:
        return False
    return fuzz.token_set_ratio(n, h) >= 88 and fuzz.partial_ratio(n, h) >= 85


def load_golden(path: str | Path, golden_id: str | None = None) -> dict[str, Any]:
    entries = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    if golden_id is None:
        return entries[0]
    for e in entries:
        if e.get("id") == golden_id:
            return e
    raise KeyError(f"golden id {golden_id!r} not in {path}")


def load_all_golden(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def _finding_text(f: dict[str, Any]) -> str:
    return f"{f.get('field', '')} {f.get('value', '')}"


def recall(golden: dict[str, Any], findings: list[dict[str, Any]]) -> tuple[float, dict[str, list[float]], list[dict[str, Any]]]:
    """Weighted recall over auto-scorable facts. Returns (recall, per-tier [hit, total], rows)."""
    tier_tot: dict[str, list[float]] = {}
    rows = []
    for fact in golden["facts"]:
        if fact.get("value_any") is None:
            continue
        tier, w = fact["tier"], float(fact.get("weight", 1))
        tier_tot.setdefault(tier, [0.0, 0.0])
        tier_tot[tier][1] += w
        hit = None
        for v in fact["value_any"]:
            for f in findings:
                if match(v, _finding_text(f)):
                    hit = f.get("source_url") or f.get("method") or "finding"
                    break
            if hit:
                break
        if hit:
            tier_tot[tier][0] += w
        rows.append({"key": fact["key"], "tier": tier, "found": bool(hit), "where": hit or ""})
    total_w = sum(v[1] for v in tier_tot.values())
    total_hit = sum(v[0] for v in tier_tot.values())
    return (total_hit / total_w if total_w else 0.0), tier_tot, rows


def _golden_by_field(golden: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for fact in golden["facts"]:
        fld = fact.get("field")
        if fld and fact.get("value_any"):
            out.setdefault(normalize(fld).replace(" ", "_"), []).append(fact)
    return out


def _facts_for_field(by_field: dict[str, list[dict[str, Any]]], finding_field: str) -> list[dict[str, Any]]:
    """A finding field maps to a golden field when equal, or when one is a suffix token of the other
    (current_employer <-> employer, prior_employer <-> employer)."""
    ff = normalize(finding_field).replace(" ", "_")
    if not ff:
        return []
    if ff in by_field:
        return by_field[ff]
    for gf, facts in by_field.items():
        g = gf.replace(" ", "_")
        if ff.endswith("_" + g) or g.endswith("_" + ff):
            return facts
    return []


def _source_path(f: dict[str, Any], workspace: Path, source_paths: dict[str, str]) -> Path | None:
    sid = f.get("source_id")
    if not sid:
        return None
    rel = source_paths.get(sid)
    if rel:
        return workspace / rel
    sdir = workspace / "sources"
    hits = (sorted(sdir.glob(f"*_{sid}_*")) + sorted(sdir.glob(f"{sid}_*"))) if sdir.exists() else []
    return hits[0] if hits else None


def provenance_failure(f: dict[str, Any], workspace: Path | None, source_paths: dict[str, str] | None = None) -> str | None:
    """Return a reason string if the finding fails provenance, None if it passes, or None with
    prov_checked False when the finding predates excerpts (no key at all)."""
    if "excerpt" not in f:
        return None
    excerpt = f.get("excerpt")
    if not excerpt:
        return "missing excerpt"
    value = f.get("value") or ""
    nv, ne = normalize(value), normalize(excerpt)
    if "@" in nv or "/" in nv:
        if nv not in ne:
            return "value not in excerpt"
    elif nv not in ne and (len(nv) > len(ne) + 8 or fuzz.partial_ratio(nv, ne) < 92):
        # same rule as admission (evidence.EvidenceStore._contains): a value longer than its excerpt
        # adds words the source never stated
        return "value not in excerpt"
    if workspace is not None and f.get("source_id") and f.get("content_hash"):
        src = _source_path(f, workspace, source_paths or {})
        if src is None or not src.exists():
            return "source file missing"
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        if digest != f["content_hash"]:
            return "content hash mismatch"
    return None


def wrong(golden: dict[str, Any], findings: list[dict[str, Any]], workspace: Path | None,
          source_paths: dict[str, str] | None = None) -> tuple[float, int, list[dict[str, Any]]]:
    """Summed penalty, count of wrong findings, and per-finding reasons."""
    by_field = _golden_by_field(golden)
    decoys = [normalize(d["marker"]) for d in golden.get("decoys", [])]
    total, count, rows = 0.0, 0, []
    for f in findings:
        reasons, pen = [], 0.0
        # Contradiction needs an exact field name match on a single-valued field: current_employer is
        # judged only against a golden current_employer fact, never against the list of past employers.
        ff = normalize(f.get("field") or "").replace(" ", "_")
        facts = by_field.get(ff, []) if ff in EXCLUSIVE_FIELDS else []
        if facts and not any(match(v, f.get("value") or "") for fact in facts for v in fact["value_any"]):
            reasons.append(f"contradicts {'/'.join(fact['key'] for fact in facts)}")
            pen += max(float(fact.get("weight", 1)) for fact in facts)
        blob = normalize(json.dumps(f, ensure_ascii=False))
        for d in decoys:
            if d and d in blob:
                reasons.append(f"decoy leak: {d}")
                pen += DECOY_PENALTY
        pf = provenance_failure(f, workspace, source_paths)
        if pf:
            reasons.append(f"provenance: {pf}")
            pen += PROVENANCE_PENALTY
        if reasons:
            count += 1
            total += pen
            rows.append({"field": f.get("field"), "value": str(f.get("value"))[:60], "penalty": pen, "reasons": reasons})
    return total, count, rows


def decoy_leaks(golden: dict[str, Any], findings: list[dict[str, Any]]) -> int:
    decoys = [normalize(d["marker"]) for d in golden.get("decoys", [])]
    n = 0
    for f in findings:
        blob = normalize(json.dumps(f, ensure_ascii=False))
        n += sum(1 for d in decoys if d and d in blob)
    return n


def score_target(golden: dict[str, Any], report: dict[str, Any], workspace: str | Path | None = None) -> dict[str, Any]:
    ws = Path(workspace) if workspace else None
    identity = report.get("identity") or {}
    status = identity.get("status") or "unresolved"
    name = identity.get("name") or ""
    resolved_id = identity.get("candidate_id") or identity.get("best_candidate_id")
    findings = list(report.get("findings") or [])
    excluded = list(report.get("excluded_findings") or [])
    admitted = [f for f in findings + excluded if (f.get("kind") in (None, "finding"))]
    source_paths = {s["id"]: s["path"] for s in (report.get("sources") or []) if s.get("id") and s.get("path")}
    if status == "resolved":
        attributed = [f for f in findings if resolved_id is None or f.get("candidate_id") in (None, resolved_id)]
    else:
        attributed = []
        # In the ambiguous band the report attributes nothing, but the scorer should judge the facts
        # recorded about the leading candidate, not those about the namesakes it correctly kept apart.
        if resolved_id and any(f.get("candidate_id") == resolved_id for f in admitted):
            admitted = [f for f in admitted if f.get("candidate_id") == resolved_id]
    prov_checked = any("excerpt" in f for f in admitted)

    expect = golden["expect_identity"]
    exp_status = expect.get("status", "resolved")
    name_ok = any(match(n, name) for n in expect.get("name_any", [])) if name else False

    row: dict[str, Any] = {
        "golden_id": golden["id"], "expect_status": exp_status, "identity_status": status,
        "identity_name": name, "identity_ok": False, "recall": 0.0, "wrong": 0.0, "wrong_count": 0,
        "decoy_leak": decoy_leaks(golden, admitted), "prov_checked": prov_checked,
        "admitted": len(admitted), "attributed": len(attributed), "net": 0.0, "branch": "",
        "tiers": {}, "recall_rows": [], "wrong_rows": [],
    }

    if exp_status == "resolved":
        if status == "resolved" and not name_ok:
            row["branch"] = "wrong_person"
            return row
        if status == "resolved":
            row["identity_ok"] = True
            r, tiers, rrows = recall(golden, attributed)
            w, wc, wrows = wrong(golden, attributed, ws, source_paths)
            net = max(0.0, r - w)
            row["branch"] = "resolved_right"
        else:
            r, tiers, rrows = recall(golden, admitted)
            w, wc, wrows = wrong(golden, admitted, ws, source_paths)
            net = NOT_RESOLVED_FACTOR * max(0.0, r - w)
            row["branch"] = "not_resolved"
        row.update(recall=round(r, 4), wrong=round(w, 4), wrong_count=wc, tiers=tiers,
                   recall_rows=rrows, wrong_rows=wrows, net=round(net, 4))
        return row

    if exp_status == "ambiguous":
        cands = identity.get("candidates") or []
        labels = [c.get("label") or c.get("name") or "" for c in cands]
        blobs = [normalize(json.dumps(c, ensure_ascii=False)) for c in cands]
        names_ok = all(any(match(n, lab) for lab in labels) for n in expect.get("name_any", []))
        markers = expect.get("expect_candidate_markers") or []
        # the ambiguity must rest on real people: two or more candidates, and when markers are given at
        # least one of them (a known slug or handle) must appear on some recorded candidate
        real = len(cands) >= 2 and (not markers or any(normalize(m) in b for m in markers for b in blobs))
        base = 1.0 if (status == "ambiguous" and names_ok and real) else 0.0
        row["identity_ok"] = base == 1.0
        leaks = row["decoy_leak"]
        row["branch"] = "ambiguous_expected"
        row["net"] = round(max(0.0, base - AMBIGUOUS_LEAK_PENALTY * leaks), 4)
        return row

    # golden expects unresolved: the invented person
    row["branch"] = "unresolved_expected"
    if status == "resolved":
        row["net"] = 0.0
        return row
    row["identity_ok"] = True
    w, wc, wrows = wrong(golden, admitted, ws, source_paths)
    row.update(wrong=round(w, 4), wrong_count=wc, wrong_rows=wrows,
               net=round(1.0 - wc / max(1, len(admitted)), 4))
    return row


def render(row: dict[str, Any], report: dict[str, Any]) -> str:
    run = report.get("run") or {}
    out = [f"# {row['golden_id']}  branch={row['branch']}  net={row['net']:.3f}",
           f"identity: {row['identity_status']} name={row['identity_name']!r} -> {'PASS' if row['identity_ok'] else 'FAIL'} (expected {row['expect_status']})",
           f"recall={row['recall']:.3f} wrong={row['wrong']:.2f} ({row['wrong_count']} findings) decoy_leak={row['decoy_leak']} "
           f"prov_checked={row['prov_checked']} admitted={row['admitted']} attributed={row['attributed']}",
           f"run: stop={run.get('stop_reason')} duration={run.get('duration_s')}s cost=${run.get('cost_usd')} tool_calls={run.get('tool_calls')}"]
    for tier in ("core", "deep", "surprise"):
        if tier in row["tiers"]:
            hit, tot = row["tiers"][tier]
            out.append(f"  {tier:9s} {hit:5.0f}/{tot:.0f} weighted ({hit / tot:.0%})")
    if row["wrong_rows"]:
        out.append("wrong findings:")
        for w in row["wrong_rows"]:
            out.append(f"  - {w['field']}={w['value']!r} penalty={w['penalty']} {w['reasons']}")
    if row["recall_rows"]:
        out.append("| fact | tier | result | matched in |")
        out.append("|---|---|---|---|")
        for r in row["recall_rows"]:
            out.append(f"| {r['key']} | {r['tier']} | {'FOUND' if r['found'] else 'miss'} | {r['where'][:70]} |")
    return "\n".join(out)


def main(argv: list[str]) -> None:
    if len(argv) < 4:
        sys.exit(__doc__)
    golden = load_golden(argv[1], argv[2])
    report = json.loads(Path(argv[3]).read_text())
    ws = argv[4] if len(argv) > 4 else None
    row = score_target(golden, report, ws)
    print(render(row, report))
    print()
    print(json.dumps({k: v for k, v in row.items() if k not in ("recall_rows", "wrong_rows", "tiers")}))


if __name__ == "__main__":
    main(sys.argv)
