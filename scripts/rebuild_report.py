"""Rebuild report.json for a run whose process died before emitting it. Everything the report needs
is already on disk (anchor.json, candidates.json, resolution.json, claims.jsonl, sources.json), which
is the point of admitting claims as they arrive: a crash loses the closing message, never the facts.

    uv run python scripts/rebuild_report.py runs/<dir>/<run_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from osint2.entities import EntityGraph  # noqa: E402
from osint2.evidence import EvidenceStore  # noqa: E402
from osint2.report import build_report  # noqa: E402
from osint2.resolution import Anchor, Candidate, Resolution  # noqa: E402
from osint2.trace import read_trace, summarize_trace  # noqa: E402
from osint2.workspace import Workspace  # noqa: E402


def main(run_dir: str) -> None:
    p = Path(run_dir)
    ws = Workspace(p.parent, p.name)
    anchor = Anchor(**(ws.read_json("anchor.json") or {}))
    cands = [Candidate(**c) for c in (ws.read_json("candidates.json") or [])]
    res = Resolution(**(ws.read_json("resolution.json") or {}))
    store = EvidenceStore(ws)
    stats = summarize_trace(read_trace(ws.trace_path))
    run = {**stats, "stop_reason": "interrupted", "rebuilt": True, "run_id": ws.run_id, "trace_path": str(ws.trace_path),
           "budget": {"calls": stats.get("tool_calls"), "max_calls": None, "usd": stats.get("cost_usd"), "max_usd": None}, **store.stats()}
    same = set(res.judge.same_person_ids) if res.judge and res.judge.verdict == "same" else set()
    report = build_report(anchor, res, cands, store, run, same)
    if "--rederive" in sys.argv:
        (ws.dir / "entities.json").unlink(missing_ok=True)
        ents = EntityGraph(ws)
        ents.ingest_target(anchor.raw)
        for c in cands:
            ents.ingest_candidate(c.id, c.label, c.names, c.handles, c.emails, c.profile_urls, [e.name for e in c.employers],
                                  [e.name for e in c.education], resolved=(res.status == "resolved" and res.best_candidate_id == c.id))
        for cl in store.claims:
            ents.ingest_claim(cl, res.best_candidate_id if res.status == "resolved" else None)
        for ev in read_trace(ws.trace_path):
            if ev.get("span") == "execute_tool" and ev.get("tool") not in ("record_claim", "record_candidate", "record_not_found", "finish"):
                a = ev.get("args") or {}
                ents.mark_explored(url=a.get("url"), handle=a.get("username"), email=a.get("email"),
                                   name=a.get("name") or (a.get("query") if ev.get("tool") in ("web_search", "openalex_lookup") else None))
        ents.persist()
    else:
        ents = EntityGraph(ws)
    report["entities"] = ents.to_report()
    ws.write_json("report.json", report)
    ws.write_json("graph.json", report["graph"])
    print(json.dumps({"identity": report["identity"]["status"], "name": report["identity"]["name"], "findings": len(report["findings"]),
                      "excluded": len(report["excluded_findings"]), "not_found": len(report["not_found"]), "cost_usd": stats.get("cost_usd")}))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
