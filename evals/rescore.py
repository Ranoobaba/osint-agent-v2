"""Re-score every ladder row from its saved workspace with the current scorer and golden file, and
rewrite results/ladder.jsonl. Use after a scorer fix or a golden correction so all rungs are judged
by the same rules. Cost, duration and stop_reason are kept from the original run.

    uv run python evals/rescore.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
from ladder import TARGETS, golden_by_id  # noqa: E402
from results import JSONL, load_rows, render_md  # noqa: E402
from score import score_target  # noqa: E402


def main() -> None:
    golden = golden_by_id()
    rows = load_rows()
    changed = 0
    out = []
    for r in rows:
        ws = Path(r.get("workspace") or "")
        gid = TARGETS.get(r.get("target"))
        if not ws.exists() or not gid or gid not in golden or not (ws / "report.json").exists():
            out.append(r)
            continue
        row = score_target(golden[gid], json.loads((ws / "report.json").read_text()), ws)
        new = dict(r, net=row["net"], identity_status=row["identity_status"], identity_ok=row["identity_ok"],
                   recall=row["recall"], wrong=row["wrong"], decoy_leak=row["decoy_leak"], branch=row["branch"],
                   prov_fail=sum(1 for w in row["wrong_rows"] if any(x.startswith("provenance") for x in w["reasons"])))
        if new["net"] != r["net"] or new["wrong"] != r["wrong"]:
            changed += 1
            print(f"{r['rung']} {r['target']} run{r.get('run_n')}: net {r['net']} -> {new['net']} wrong {r['wrong']} -> {new['wrong']}")
        out.append(new)
    JSONL.write_text("".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in out))
    render_md()
    print(f"rescored {len(out)} rows, {changed} changed")


if __name__ == "__main__":
    main()
