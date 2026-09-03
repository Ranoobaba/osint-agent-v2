"""Copy a finished run into examples/<slug>/ with its input, report, trace, graph and sources, then
redact recovered private emails so the folder can be committed.

    uv run python scripts/make_example.py runs/rung9/michael_jordan/<run_id> michael_jordan
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact_example import redact_dir  # noqa: E402

KEEP = ("input.json", "report.json", "trace.jsonl", "graph.json", "sources.json", "claims.jsonl", "resolution.json", "candidates.json", "anchor.json")


def main(run_dir: str, slug: str) -> None:
    src = Path(run_dir)
    dst = Path("examples") / slug
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for name in KEEP:
        if (src / name).exists():
            shutil.copy(src / name, dst / name)
    if (src / "sources").exists():
        shutil.copytree(src / "sources", dst / "sources")
    n = redact_dir(dst)
    print(f"examples/{slug}: copied {len(list(dst.rglob('*')))} files, redacted {n} private email(s)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
