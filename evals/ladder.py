"""Run one rung of the ladder: a configuration (tool set, flags) across the eval targets with
repeats, score every run, append rows to results/ladder.jsonl, re-render results/ladder.md.

    uv run python evals/ladder.py --rung 2                 # the preset, all its targets and repeats
    uv run python evals/ladder.py --rung 2 --targets baseline --repeats 1 --dev   # a dev run
    uv run python evals/ladder.py --plan                   # print presets and the cost estimate table

Rung presets follow the plan file. Targets are golden ids mapped to short names below. The runner
refuses to start a rung whose estimate would push ladder spend past the cap, and applies the
pre-declared cut order instead of guessing.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from osint2.agent import run_investigation  # noqa: E402
from osint2.config import Settings  # noqa: E402
from results import append_row, load_rows, noise_band, rung_summary, spend  # noqa: E402
from score import load_all_golden, score_target  # noqa: E402

GOLDEN_PATH = ROOT / "evals" / "golden.local.jsonl"
LADDER_CAP_USD = 70.0
DEV_CAP_USD = 10.0

# short target name -> golden id
TARGETS = {
    "baseline": "syed-rayyan-ali-self",
    "email_only": "self-email-only",
    "handle_only": "self-handle-only",
    "collision_key": "collision-with-key",
    "collision_nokey": "collision-without-key",
    "sarah_chen": "sarah-chen-figma",
    "michael_jordan": "michael-jordan-berkeley",
    "ariglad_cto": "ariglad-cto",
    "invented": "invented-zero-hit",
}
ALL = list(TARGETS)
SUBSET4 = ["baseline", "collision_key", "michael_jordan", "invented"]
FREE = "github,gravatar,wayback,whatsmyname"

RUNGS: dict[str, dict[str, Any]] = {
    "1": {"env": {"TOOLS": "none", "DEEP_DIVE": "0"}, "targets": ALL, "repeats": {"baseline": 3}, "compare_to": None, "estimate": 1.5},
    "2": {"env": {"TOOLS": FREE, "DEEP_DIVE": "0"}, "targets": ALL, "repeats": {"baseline": 3}, "compare_to": "1", "estimate": 10.0},
    "3": {"env": {"TOOLS": FREE, "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": ALL, "repeats": {}, "compare_to": "2", "estimate": 5.0},
    "4": {"env": {"TOOLS": FREE + ",perplexity", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": SUBSET4, "repeats": {}, "compare_to": "3", "estimate": 4.0},
    "5": {"env": {"TOOLS": FREE + ",exa", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": SUBSET4, "repeats": {}, "compare_to": "3", "estimate": 4.0},
    "6": {"env": {"TOOLS": FREE + ",firecrawl", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": SUBSET4, "repeats": {}, "compare_to": "3", "estimate": 4.0},
    "7": {"env": {"TOOLS": FREE + ",perplexity,exa", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": SUBSET4, "repeats": {}, "compare_to": "best(4,5)", "estimate": 4.0, "cut_order": 2},
    "8": {"env": {"TOOLS": FREE + ",perplexity,exa,firecrawl", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1"}, "targets": ALL, "repeats": {"baseline": 3}, "compare_to": "3", "estimate": 12.0},
    "8s40": {"env": {"TOOLS": FREE + ",perplexity,exa,firecrawl", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1", "MAX_TOOL_CALLS": "40", "MAX_USD": "2.5", "MAX_SECONDS": "960"}, "targets": ["baseline"], "repeats": {}, "compare_to": "8", "estimate": 2.5, "cut_order": 4},
    "8s80": {"env": {"TOOLS": FREE + ",perplexity,exa,firecrawl", "DEEP_DIVE": "0", "NUDGE_INPUT_SHAPE": "1", "MAX_TOOL_CALLS": "80", "MAX_USD": "5", "MAX_SECONDS": "1920"}, "targets": ["baseline"], "repeats": {}, "compare_to": "8s40", "estimate": 5.0, "cut_order": 1},
    "9": {"env": {"TOOLS": FREE + ",perplexity,exa,firecrawl", "DEEP_DIVE": "1", "NUDGE_INPUT_SHAPE": "1"}, "targets": ALL, "repeats": {"baseline": 3, "collision_nokey": 3, "invented": 3}, "compare_to": "8", "estimate": 17.0},
}
DEFAULT_ENV = {"MAX_TOOL_CALLS": "20", "MAX_USD": "1.25", "MAX_SECONDS": "480"}


def golden_by_id() -> dict[str, dict[str, Any]]:
    return {g["id"]: g for g in load_all_golden(GOLDEN_PATH)}


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


async def one_run(rung: str, target: str, golden: dict[str, Any], env: dict[str, str], run_n: int, compare_to: str | None,
                  sem: asyncio.Semaphore, dev: bool, note: str) -> dict[str, Any]:
    async with sem:
        settings = Settings.from_env(env)
        runs_dir = ROOT / "runs" / f"rung{rung}" / target
        report, ws = await run_investigation(golden["target"], settings, runs_dir=runs_dir)
        row = score_target(golden, report, ws.dir)
        run = report["run"]
        out = {
            "rung": ("dev-" if dev else "") + rung, "compare_to": compare_to, "target": target, "run_n": run_n,
            "net": row["net"], "identity_status": row["identity_status"], "identity_ok": row["identity_ok"],
            "recall": row["recall"], "wrong": row["wrong"],
            "prov_fail": sum(1 for w in row["wrong_rows"] if any(r.startswith("provenance") for r in w["reasons"])),
            "decoy_leak": row["decoy_leak"], "proposed_claims": run.get("proposed"), "admitted": run.get("admitted"),
            "rejected": run.get("rejected"), "cost_usd": run.get("cost_usd"), "duration_s": run.get("duration_s"),
            "stop_reason": run.get("stop_reason"), "tool_calls": (run.get("budget") or {}).get("calls", run.get("tool_calls")), "git_sha": git_sha(),
            "unsupported_candidates": run.get("unsupported_candidates"),
            "note": note, "run_id": ws.run_id, "branch": row["branch"], "workspace": str(ws.dir),
            "method_counts": _method_counts(report),
        }
        append_row(out)
        print(f"  {out['rung']} {target} run{run_n}: net={out['net']:.3f} identity={out['identity_status']} "
              f"recall={out['recall']:.2f} wrong={out['wrong']:.1f} admitted={out['admitted']} rejected={out['rejected']} "
              f"calls={out['tool_calls']} ${float(out['cost_usd'] or 0):.2f} {out['stop_reason']} ({ws.run_id})", flush=True)
        return out


def _method_counts(report: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in report.get("findings", []):
        counts[f.get("method") or "?"] = counts.get(f.get("method") or "?", 0) + 1
    return counts


def plan_text() -> str:
    lines = ["| rung | tools | deep_dive | targets | runs | estimate | compare_to |", "|---|---|---|---|---|---|---|"]
    for k, r in RUNGS.items():
        runs = sum(r["repeats"].get(t, 1) for t in r["targets"])
        lines.append(f"| {k} | {r['env'].get('TOOLS')} | {r['env'].get('DEEP_DIVE')} | {len(r['targets'])} | {runs} | ${r['estimate']:.2f} | {r['compare_to']} |")
    sp = spend()
    lines.append(f"\nLadder spend so far ${sp['ladder']:.2f} of ${LADDER_CAP_USD:.0f}; dev ${sp['dev']:.2f} of ${DEV_CAP_USD:.0f}.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rung", help="preset id, e.g. 2 or 8s40")
    ap.add_argument("--targets", help="comma list of short names to restrict to")
    ap.add_argument("--repeats", type=int, help="override repeats for every selected target")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--dev", action="store_true", help="tag as a development run; counts against the dev bucket")
    ap.add_argument("--note", default="")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--force", action="store_true", help="ignore the spend cap check")
    args = ap.parse_args()
    if args.plan or not args.rung:
        print(plan_text())
        return
    preset = RUNGS[args.rung]
    targets = [t.strip() for t in args.targets.split(",")] if args.targets else preset["targets"]
    golden = golden_by_id()
    missing = [t for t in targets if TARGETS[t] not in golden]
    if missing:
        print(f"skipping targets without a golden entry yet: {missing}", file=sys.stderr)
        targets = [t for t in targets if t not in missing]
    if not targets:
        sys.exit("no targets to run")
    env = {**DEFAULT_ENV, **preset["env"]}
    sp = spend()
    est = preset["estimate"] * (len(targets) / max(1, len(preset["targets"])))
    if not args.dev and not args.force and sp["ladder"] + est > LADDER_CAP_USD:
        sys.exit(f"refusing: ladder spend ${sp['ladder']:.2f} + estimate ${est:.2f} would pass the ${LADDER_CAP_USD:.0f} cap. "
                 f"Apply the cut order (8s80, then 7, then rung 9 extra repeats, then 8s40, then reruns) or pass --force.")
    if args.dev and sp["dev"] > DEV_CAP_USD:
        print(f"warning: dev spend ${sp['dev']:.2f} is past the ${DEV_CAP_USD:.0f} dev bucket", file=sys.stderr)
    jobs = []
    for t in targets:
        n = args.repeats or preset["repeats"].get(t, 1)
        for i in range(1, n + 1):
            jobs.append((t, i))
    print(f"rung {args.rung}: {len(jobs)} runs over {len(targets)} targets, env {preset['env']}, estimate ${est:.2f}")
    sem = asyncio.Semaphore(args.concurrency)

    async def go():
        return await asyncio.gather(*[one_run(args.rung, t, golden[TARGETS[t]], env, i, preset["compare_to"], sem, args.dev, args.note)
                                      for t, i in jobs], return_exceptions=True)
    results = asyncio.run(go())
    errors = [r for r in results if isinstance(r, Exception)]
    for e in errors:
        print(f"  run failed: {type(e).__name__}: {e}", file=sys.stderr)
    rows = load_rows()
    summary = rung_summary(rows)
    key = ("dev-" if args.dev else "") + args.rung
    if key in summary:
        s = summary[key]
        print(f"\nrung {key}: score={s['score']:.3f} min={s['min']:.3f} runs={s['runs']} cost=${s['cost_usd']:.2f} "
              f"band={noise_band(summary):.3f} identity {s['identity_pass']}/{s['runs']} prov_fail={s['prov_fail']} decoy={s['decoy_leak']}")
    print(f"ladder spend ${spend()['ladder']:.2f}, dev ${spend()['dev']:.2f}. Table: evals/results/ladder.md")


if __name__ == "__main__":
    main()
