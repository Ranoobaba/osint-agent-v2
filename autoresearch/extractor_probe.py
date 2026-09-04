"""Offline probe of the review's top optimization: a per-source extractor. For one saved run, feed each
stored source to a cheap model with structured output, ask for claims with verbatim quotes, admit them
through the SAME EvidenceStore.admit gate into a scratch copy of the workspace, and score recall
against golden before and after. Costs about $0.10 per run (Sonnet, ~16 sources).

    uv run python autoresearch/extractor_probe.py runs/ar1/michael_jordan/<run_id> michael_jordan
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from ladder import TARGETS, golden_by_id  # noqa: E402
from osint2.config import Settings  # noqa: E402
from osint2.evidence import EvidenceStore  # noqa: E402
from osint2.llm import OpenRouterClient  # noqa: E402
from osint2.report import build_report  # noqa: E402
from osint2.resolution import Anchor, Candidate, Resolution  # noqa: E402
from osint2.trace import TraceWriter  # noqa: E402
from osint2.workspace import Workspace  # noqa: E402
from score import score_target  # noqa: E402

EXTRACT_PROMPT = """You extract facts about ONE person from ONE page. Return only a JSON object {"claims": [...]}.
Each claim: {"field": snake_case, "value": the fact as stated, "excerpt": the exact line from the page that states it,
"category": one of identity, contact, professional, education, online_presence, projects, connections, personal, sensitive, other}.
Rules: only facts the page states about the named person; one value per claim; the excerpt must be copied verbatim and must
contain the value; skip anything about other people unless it is a relationship to this person (then field starts with
'connection_' or 'collaborator'); skip navigation, boilerplate, and facts you infer rather than read."""

SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "items": {"type": "object", "properties": {
    "field": {"type": "string"}, "value": {"type": "string"}, "excerpt": {"type": "string"}, "category": {"type": "string"}},
    "required": ["field", "value", "excerpt", "category"], "additionalProperties": False}}}, "required": ["claims"], "additionalProperties": False}


async def main(run_dir: str, target: str, model: str) -> None:
    src = Path(run_dir)
    dst = ROOT / "runs" / "extractor_probe" / src.name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    ws = Workspace(dst.parent, dst.name)
    golden = golden_by_id()[TARGETS[target]]
    anchor = Anchor(**(ws.read_json("anchor.json") or {}))
    cands = [Candidate(**c) for c in (ws.read_json("candidates.json") or [])]
    res = Resolution(**(ws.read_json("resolution.json") or {}))
    store = EvidenceStore(ws)
    before = score_target(golden, json.loads((src / "report.json").read_text()), src)
    settings = Settings.from_env()
    trace = TraceWriter(dst / "probe_trace.jsonl", ws.run_id)
    llm = OpenRouterClient(settings, trace)
    person = next((c for c in cands if c.id == res.best_candidate_id), None)
    who = f"{person.label} (names {person.names}, handles {person.handles}, emails {person.emails})" if person else anchor.raw
    admitted = rejected = 0
    cost = 0.0
    sem = asyncio.Semaphore(4)

    async def one(sid: str) -> None:
        nonlocal admitted, rejected, cost
        text = store.source_text(sid)[:12000]
        async with sem:
            try:
                r = await llm.chat([{"role": "system", "content": EXTRACT_PROMPT},
                                    {"role": "user", "content": f"Person: {who}\n\nPage (source {sid}):\n{text}"}],
                                   tools=None, model=model, thread="extractor", reasoning=False,
                                   response_format={"type": "json_schema", "json_schema": {"name": "claims", "strict": True, "schema": SCHEMA}})
            except Exception as exc:  # noqa: BLE001
                print("  extractor error", sid, type(exc).__name__)
                return
        cost += r.usage.get("cost_usd") or 0.0
        try:
            claims = json.loads(r.text).get("claims", [])
        except ValueError:
            return
        for c in claims[:25]:
            c = {**c, "source_id": sid, "candidate_id": res.best_candidate_id}
            claim, reason = store.admit(c, step=99, thread="extractor", default_candidate=res.best_candidate_id)
            if claim:
                admitted += 1
            else:
                rejected += 1

    await asyncio.gather(*[one(sid) for sid in list(store.sources)])
    run = {"stop_reason": "probe", "run_id": ws.run_id, "budget": {"calls": 0}, **store.stats()}
    same = set(res.judge.same_person_ids) if res.judge and res.judge.verdict == "same" else set()
    report = build_report(anchor, res, cands, store, run, same)
    ws.write_json("report.json", report)
    after = score_target(golden, report, dst)
    print(json.dumps({"target": target, "model": model, "sources": len(store.sources), "extractor_admitted": admitted, "extractor_rejected": rejected,
                      "extractor_cost_usd": round(cost, 4), "findings_before": len(json.loads((src / 'report.json').read_text())["findings"]),
                      "findings_after": len(report["findings"]), "recall_before": before["recall"], "recall_after": after["recall"],
                      "net_before": before["net"], "net_after": after["net"], "wrong_after": after["wrong"], "decoy_after": after["decoy_leak"],
                      "prov_fail_after": sum(1 for w in after["wrong_rows"] if any(x.startswith("provenance") for x in w["reasons"]))}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else os.environ.get("EXTRACTOR_MODEL", "anthropic/claude-sonnet-5")))
