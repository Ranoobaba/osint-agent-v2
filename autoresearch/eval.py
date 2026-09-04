"""The autoresearch eval: run the mini-eval at the shipped configuration, score it with the ladder's
scorer, append one row to autoresearch/results.tsv, and enforce the spend cap.

    uv run python autoresearch/eval.py --note "baseline"
    uv run python autoresearch/eval.py --note "..." --targets michael_jordan,invented   # cheaper subset

Rows: iteration, commit, net, band_ok, prov_fail, decoy_leak, rejection_rate, findings_per_call,
usd_per_finding, mean_cost, mean_duration, status (pending until the agent sets keep/revert), note.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from osint2.agent import run_investigation  # noqa: E402
from osint2.config import Settings  # noqa: E402
from score import load_all_golden, score_target  # noqa: E402

AR = ROOT / "autoresearch"
RESULTS = AR / "results.tsv"
SPEND = AR / "spend.json"
CAP = float(os.environ.get("AUTORESEARCH_CAP_USD", "6"))
BAND = 0.03
TARGETS = {"michael_jordan": "michael-jordan-berkeley", "ariglad_cto": "ariglad-cto", "invented": "invented-zero-hit"}
COLS = ["iteration", "commit", "net", "delta_vs_best_kept", "prov_fail", "decoy_leak", "rejection_rate", "findings_per_call",
        "usd_per_finding", "mean_cost", "mean_duration", "status", "note", "ts", "runs"]


def spend() -> float:
    return json.loads(SPEND.read_text())["usd"] if SPEND.exists() else 0.0


def add_spend(usd: float) -> None:
    SPEND.write_text(json.dumps({"usd": round(spend() + usd, 4)}))


def rows() -> list[dict[str, str]]:
    if not RESULTS.exists():
        return []
    lines = RESULTS.read_text().splitlines()
    return [dict(zip(COLS, ln.split("\t"))) for ln in lines[1:] if ln.strip()]


def best_kept() -> float | None:
    kept = [float(r["net"]) for r in rows() if r.get("status") == "keep"]
    return max(kept) if kept else None


async def run_all(targets: list[str], golden: dict, settings: Settings, iteration: int) -> list[dict]:
    sem = asyncio.Semaphore(3)

    async def one(t: str) -> dict:
        async with sem:
            report, ws = await run_investigation(golden[TARGETS[t]]["target"], settings, runs_dir=ROOT / "runs" / f"ar{iteration}" / t)
            row = score_target(golden[TARGETS[t]], report, ws.dir)
            run = report["run"]
            return {"target": t, "net": row["net"], "prov_fail": sum(1 for w in row["wrong_rows"] if any(x.startswith("provenance") for x in w["reasons"])),
                    "decoy_leak": row["decoy_leak"], "proposed": run.get("proposed") or 0, "rejected": run.get("rejected") or 0,
                    "findings": len(report["findings"]), "calls": run["budget"]["calls"], "cost": run.get("cost_usd") or 0.0,
                    "duration": run.get("duration_s") or 0.0, "run_id": ws.run_id}
    return await asyncio.gather(*[one(t) for t in targets])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", required=True)
    ap.add_argument("--targets", default=",".join(TARGETS))
    args = ap.parse_args()
    if (AR / "STOP").exists():
        sys.exit("STOP file present; not running")
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    est = 0.5 * len(targets)
    if spend() + est > CAP:
        sys.exit(f"refusing: autoresearch spend ${spend():.2f} + est ${est:.2f} would pass the ${CAP:.0f} cap")
    golden = {g["id"]: g for g in load_all_golden(ROOT / "evals" / "golden.local.jsonl")}
    settings = Settings.from_env()
    iteration = len(rows()) + 1
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", ".env"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    results = asyncio.run(run_all(targets, golden, settings, iteration))
    net = sum(r["net"] for r in results) / len(results)
    prov = sum(r["prov_fail"] for r in results); leak = sum(r["decoy_leak"] for r in results)
    proposed = sum(r["proposed"] for r in results); rejected = sum(r["rejected"] for r in results)
    findings = sum(r["findings"] for r in results); calls = sum(r["calls"] for r in results)
    cost = sum(r["cost"] for r in results); dur = sum(r["duration"] for r in results) / len(results)
    add_spend(cost)
    bk = best_kept()
    delta = "" if bk is None else f"{net - bk:+.3f}"
    band_ok = bk is None or (net - bk) > BAND
    verdict = "keep" if (band_ok and prov == 0 and leak == 0 and cost / len(results) <= settings.max_usd) else "revert"
    if bk is None:
        verdict = "keep"  # the baseline is kept by definition
    row = [str(iteration), commit + ("+dirty" if dirty else ""), f"{net:.4f}", delta, str(prov), str(leak),
           f"{(rejected / proposed) if proposed else 0:.3f}", f"{(findings / calls) if calls else 0:.2f}", f"{(cost / findings) if findings else 0:.3f}",
           f"{cost / len(results):.3f}", f"{dur:.0f}", verdict, args.note.replace("\t", " "), datetime.now(timezone.utc).isoformat(timespec="seconds"),
           ";".join(f"{r['target']}={r['net']:.3f}@{r['run_id']}" for r in results)]
    if not RESULTS.exists():
        RESULTS.write_text("\t".join(COLS) + "\n")
    with RESULTS.open("a") as f:
        f.write("\t".join(row) + "\n")
    print("\t".join(COLS)); print("\t".join(row))
    print(f"\nverdict by the hard rules: {verdict.upper()}  (net {net:.3f}, best kept {bk}, band {BAND}, prov_fail {prov}, decoy {leak}, mean cost ${cost/len(results):.2f})")
    print(f"autoresearch spend ${spend():.2f} of ${CAP:.0f}")


if __name__ == "__main__":
    main()
