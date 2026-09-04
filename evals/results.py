"""Results table for the ladder. One JSON line per (rung, target, run) in results/ladder.jsonl,
rendered to results/ladder.md. ladder.py appends rows; this module owns the file formats so the
Stage 0 calibration row and every rung row look the same."""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent / "results"
JSONL = RESULTS_DIR / "ladder.jsonl"
MD = RESULTS_DIR / "ladder.md"
SPEND = RESULTS_DIR / "spend.json"

ROW_KEYS = ["rung", "compare_to", "target", "run_n", "net", "identity_status", "identity_ok", "recall", "wrong",
            "prov_fail", "decoy_leak", "proposed_claims", "admitted", "rejected", "cost_usd", "duration_s",
            "stop_reason", "tool_calls", "git_sha", "ts", "note"]


def append_row(row: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    row = {k: row.get(k) for k in ROW_KEYS} | {k: v for k, v in row.items() if k not in ROW_KEYS}
    row["ts"] = row.get("ts") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    rung = str(row.get("rung", ""))
    if not rung.startswith("v1"):  # v1 calibration rows are v1 money, not v2 spend
        add_spend("dev" if rung.startswith("dev") else "ladder", float(row.get("cost_usd") or 0.0))
    render_md()


def add_spend(bucket: str, usd: float) -> dict[str, float]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    spend = json.loads(SPEND.read_text()) if SPEND.exists() else {"ladder": 0.0, "dev": 0.0}
    spend[bucket] = round(spend.get(bucket, 0.0) + usd, 4)
    SPEND.write_text(json.dumps(spend, indent=2))
    return spend


def spend() -> dict[str, float]:
    return json.loads(SPEND.read_text()) if SPEND.exists() else {"ladder": 0.0, "dev": 0.0}


def load_rows() -> list[dict[str, Any]]:
    if not JSONL.exists():
        return []
    return [json.loads(line) for line in JSONL.read_text().splitlines() if line.strip()]


def rung_summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per rung: score = mean over targets of (median over that target's runs), plus min, cost, time."""
    by_rung: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_rung[str(r["rung"])][str(r["target"])].append(r)
    out = {}
    per_target_by_rung: dict[str, dict[str, float]] = {}
    for rung, targets in by_rung.items():
        per_target = {t: statistics.median(float(x["net"] or 0) for x in runs) for t, runs in targets.items()}
        per_target_by_rung[rung] = per_target
        all_runs = [x for runs in targets.values() for x in runs]
        baseline_runs = [float(x["net"] or 0) for t, runs in targets.items() if t == "baseline" for x in runs]
        out[rung] = {
            "score": round(statistics.mean(per_target.values()), 4) if per_target else 0.0,
            "min": round(min(per_target.values()), 4) if per_target else 0.0,
            "targets": len(per_target),
            "runs": len(all_runs),
            "spread": round(max(baseline_runs) - min(baseline_runs), 4) if len(baseline_runs) > 1 else None,
            "cost_usd": round(sum(float(x.get("cost_usd") or 0) for x in all_runs), 2),
            "duration_s": round(sum(float(x.get("duration_s") or 0) for x in all_runs)),
            "compare_to": next((x.get("compare_to") for x in all_runs if x.get("compare_to")), None),
            "identity_pass": sum(1 for x in all_runs if x.get("identity_ok")),
            "prov_fail": sum(int(x.get("prov_fail") or 0) for x in all_runs),
            "decoy_leak": sum(int(x.get("decoy_leak") or 0) for x in all_runs),
            "per_target": per_target,
        }
    # The comparison is always on the same target set: a subset rung is compared against the
    # comparison rung restricted to that subset. Alongside the mean delta, a paired statistic: how
    # many targets moved up vs down, and the sign-test probability of at least that many ups under
    # the null of no effect, so one target swinging cannot carry a rung on its own.
    for rung, s in out.items():
        cmp = s.get("compare_to")
        if cmp and str(cmp) in per_target_by_rung:
            common = [t for t in s["per_target"] if t in per_target_by_rung[str(cmp)]]
            if common:
                s["compare_score"] = round(statistics.mean(per_target_by_rung[str(cmp)][t] for t in common), 4)
                s["compare_self"] = round(statistics.mean(s["per_target"][t] for t in common), 4)
                s["compare_targets"] = len(common)
                deltas = [s["per_target"][t] - per_target_by_rung[str(cmp)][t] for t in common]
                ups = sum(1 for d in deltas if d > 0.03); downs = sum(1 for d in deltas if d < -0.03)
                n = ups + downs
                from math import comb
                p_sign = sum(comb(n, k) for k in range(ups, n + 1)) / (2 ** n) if n else 1.0
                s["paired"] = {"up": ups, "down": downs, "flat": len(common) - n, "p_sign": round(p_sign, 3)}
    return out


def noise_band(summary: dict[str, dict[str, Any]], floor: float = 0.03) -> float:
    """Largest within-rung spread of baseline repeats over ladder rungs only (dev and v1 rows excluded)."""
    spreads = [s["spread"] for k, s in summary.items() if s.get("spread") is not None
               and not str(k).startswith(("dev", "v1"))]
    return round(max([floor] + spreads), 4)


def render_md() -> str:
    rows = load_rows()
    summary = rung_summary(rows)
    band = noise_band(summary)
    sp = spend()
    lines = ["# Ladder results", "",
             f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. Noise band {band:.3f} "
             f"(largest within-rung spread of baseline repeats, floor 0.03). "
             f"Ladder spend ${sp.get('ladder', 0):.2f}, dev spend ${sp.get('dev', 0):.2f}.", "",
             "| rung | score | min | vs | delta | moved | paired up/down (p) | targets | runs | identity pass | prov fail | decoy leak | cost | time |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for rung, s in summary.items():
        cmp = s.get("compare_to")
        delta = moved = ""
        if s.get("compare_score") is not None:
            d = s["compare_self"] - s["compare_score"]
            delta = f"{d:+.3f} on {s['compare_targets']}"
            moved = "yes" if d > band else "no"
        pr = s.get("paired"); paired = f"{pr['up']}/{pr['down']} ({pr['p_sign']})" if pr else ""
        lines.append(f"| {rung} | {s['score']:.3f} | {s['min']:.3f} | {cmp or ''} | {delta} | {moved} | {paired} | {s['targets']} | {s['runs']} | "
                     f"{s['identity_pass']}/{s['runs']} | {s['prov_fail']} | {s['decoy_leak']} | ${s['cost_usd']:.2f} | {s['duration_s']}s |")
    lines += ["", "## Per run", "",
              "| rung | target | run | net | identity | recall | wrong | prov fail | decoy | admitted | rejected | calls | cost | time | stop | sha | note |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['rung']} | {r['target']} | {r.get('run_n', 1)} | {float(r['net'] or 0):.3f} | "
                     f"{r.get('identity_status')}{' ok' if r.get('identity_ok') else ''} | {float(r.get('recall') or 0):.3f} | "
                     f"{float(r.get('wrong') or 0):.1f} | {r.get('prov_fail') or 0} | {r.get('decoy_leak') or 0} | {r.get('admitted') or 0} | "
                     f"{r.get('rejected') or 0} | {r.get('tool_calls') or 0} | ${float(r.get('cost_usd') or 0):.2f} | "
                     f"{int(float(r.get('duration_s') or 0))}s | {r.get('stop_reason') or ''} | {str(r.get('git_sha') or '')[:7]} | {r.get('note') or ''} |")
    text = "\n".join(lines) + "\n"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MD.write_text(text)
    return text
