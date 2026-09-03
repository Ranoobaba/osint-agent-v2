"""One directory per run. Everything the agent reads or writes lives here so a run can be
inspected, restored, or copied into examples/ as is."""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return s[:limit] or "item"


class Workspace:
    def __init__(self, root: Path, run_id: str):
        self.run_id = run_id
        self.dir = root / run_id
        self.sources_dir = self.dir / "sources"
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    @property
    def trace_path(self) -> Path:
        return self.dir / "trace.jsonl"

    def write_json(self, name: str, data: Any) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return path

    def read_json(self, name: str) -> Any | None:
        path = self.dir / name
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def write_text(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def write_source(self, kind: str, label: str, text: str) -> str:
        """Store a raw tool result under sources/ and return the path relative to the run dir."""
        self._counter += 1
        name = f"{self._counter:03d}_{kind}_{_slug(label)}.md"
        (self.sources_dir / name).write_text(text)
        return f"sources/{name}"
