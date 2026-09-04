"""J_replay: the ladder's net score recomputed over every saved scored run by replaying its stored
claims, candidates and anchor through the CURRENT code (report builder, resolver, dedupe, entity
graph), then scoring against golden. Costs nothing. Sees any code-side change; is blind to changes
that alter what the model does next (prompts, tools).

    uv run python autoresearch/replay.py            # prints per-target means and the hard-constraint check
    uv run python autoresearch/replay.py --save baseline_replay.json

Hard constraints (never terms in the objective): identity_ok must not drop on any run that had it,
prov_fail must stay 0, decoy_leak must stay 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from ladder import TARGETS, golden_by_id  # noqa: E402
from osint2.evidence import EvidenceStore  # noqa: E402
from osint2.report import build_report  # noqa: E402
from osint2.resolution import Anchor, Candidate, Resolution, apply_judge, resolve  # noqa: E402
from osint2.trace import read_trace, summarize_trace  # noqa: E402
from osint2.workspace import Workspace  # noqa: E402
from results import load_rows  # noqa: E402
from score import score_target  # noqa: E402


def replay_run(ws_dir: Path, golden: dict, rescore_identity: bool) -> dict | None:
    ws = Workspace(ws_dir.parent, ws_dir.name)
    if not (ws.dir / "claims.jsonl").exists() and not (ws.dir / "report.json").exists():
        return None
    anchor = Anchor(**(ws.read_json("anchor.json") or {}))
    cands = [Candidate(**c) for c in (ws.read_json("candidates.json") or [])]
    res = Resolution(**(ws.read_json("resolution.json") or {}))
    if rescore_identity and cands:
        res2 = resolve(anchor, cands)
        if res.judge:
            res2 = apply_judge(res2, res.judge)
        res = res2
    store = EvidenceStore(ws)
    stats = summarize_trace(read_trace(ws.trace_path))
    run = {**stats, "stop_reason": "replay", "run_id": ws.run_id, "budget": {"calls": stats.get("tool_calls")}, **store.stats()}
    same = set(res.judge.same_person_ids) if res.judge and res.judge.verdict == "same" else set()
    report = build_report(anchor, res, cands, store, run, same)
    row = score_target(golden, report, ws.dir)
    return {"net": row["net"], "identity_ok": row["identity_ok"], "status": row["identity_status"],
            "prov_fail": sum(1 for w in row["wrong_rows"] if any(x.startswith("provenance") for x in w["reasons"])),
            "decoy_leak": row["decoy_leak"], "recall": row["recall"], "wrong": row["wrong"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save")
    ap.add_argument("--compare", help="a saved replay json to diff against")
    ap.add_argument("--rescore-identity", action="store_true", help="re-run resolve() on the saved candidates (for resolver experiments); default keeps the recorded resolution")
    args = ap.parse_args()
    golden = golden_by_id()
    rows = [r for r in load_rows() if not str(r["rung"]).startswith(("dev", "v1")) and r.get("workspace")]
    out = {}
    for r in rows:
        gid = TARGETS.get(r["target"])
        if not gid or gid not in golden:
            continue
        rep = replay_run(Path(r["workspace"]), golden[gid], args.rescore_identity)
        if rep:
            out[f"{r['rung']}/{r['target']}/{r.get('run_n', 1)}"] = {**rep, "recorded_net": float(r["net"]), "recorded_identity_ok": bool(r.get("identity_ok"))}
    per_target: dict[str, list[float]] = defaultdict(list)
    for k, v in out.items():
        per_target[k.split("/")[1]].append(v["net"])
    mean = sum(v["net"] for v in out.values()) / max(1, len(out))
    lost = [k for k, v in out.items() if v["recorded_identity_ok"] and not v["identity_ok"]]
    gained = [k for k, v in out.items() if not v["recorded_identity_ok"] and v["identity_ok"]]
    prov = sum(v["prov_fail"] for v in out.values()); leak = sum(v["decoy_leak"] for v in out.values())
    print(f"J_replay over {len(out)} runs: mean net {mean:.4f}   prov_fail {prov}   decoy_leak {leak}")
    print("per target:", {t: round(sum(v) / len(v), 3) for t, v in sorted(per_target.items())})
    print(f"identity constraint: lost {len(lost)} {lost[:6]}   gained {len(gained)} {gained[:6]}")
    if args.compare:
        base = json.loads(Path(args.compare).read_text())
        bm = sum(v["net"] for v in base.values()) / max(1, len(base))
        diffs = [(k, base[k]["net"], v["net"]) for k, v in out.items() if k in base and abs(base[k]["net"] - v["net"]) > 1e-6]
        print(f"vs {args.compare}: mean {bm:.4f} -> {mean:.4f} ({mean - bm:+.4f}); {len(diffs)} runs changed")
        for k, a, b in diffs[:15]:
            print(f"  {k}: {a:.3f} -> {b:.3f}")
    if args.save:
        Path(args.save).write_text(json.dumps(out, indent=1))
        print("saved", args.save)


if __name__ == "__main__":
    main()
