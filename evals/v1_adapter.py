"""Map a v1 report.json (no excerpt or content_hash on findings) into the v2 report shape so the
new scorer can be calibrated against the old 53% number. Used only for the Stage 0 calibration.

    uv run python evals/v1_adapter.py <v1_report.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def adapt(v1: dict[str, Any]) -> dict[str, Any]:
    identity = dict(v1.get("identity") or {})
    identity.setdefault("status", "unresolved")
    identity.setdefault("candidate_id", identity.get("best_candidate_id") or identity.get("candidate_id"))
    identity.setdefault("candidates", [])

    def strip(f: dict[str, Any]) -> dict[str, Any]:
        g = {k: v for k, v in f.items() if k not in ("excerpt", "content_hash", "source_id")}
        g.setdefault("kind", "finding")
        return g

    return {
        "target": v1.get("target"),
        "run_id": v1.get("run_id"),
        "identity": identity,
        "findings": [strip(f) for f in v1.get("findings") or []],
        "excluded_findings": [strip(f) for f in v1.get("excluded_findings") or []],
        "not_found": v1.get("not_found") or [],
        "conflicts": v1.get("conflicts") or [],
        "synthesis": v1.get("synthesis") or [],
        "run": v1.get("run") or {},
        "adapted_from": "v1",
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    out = adapt(json.loads(Path(sys.argv[1]).read_text()))
    Path(sys.argv[2]).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"wrote {sys.argv[2]}: {len(out['findings'])} findings, identity {out['identity'].get('status')}")
