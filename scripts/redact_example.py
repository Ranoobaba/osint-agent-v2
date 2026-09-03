"""Redact emails that the run recovered from commit metadata or Gravatar and that appear on no public
page. Each such address is replaced, everywhere in the example folder, by 'redacted:<sha256 prefix>'.
The claim's content_hash stays as recorded, so a reader can still see that the claim was admitted
against a hashed source; the README explains that the source text differs by exactly this substitution.

    uv run python scripts/redact_example.py examples/<slug>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PRIVATE_METHODS = {"github_commit_email", "gravatar"}
PUBLIC_METHODS = {"web_search", "exa_contents", "fetch_page", "wayback"}


def private_emails(example_dir: Path) -> set[str]:
    report = json.loads((example_dir / "report.json").read_text())
    findings = report.get("findings", []) + report.get("excluded_findings", [])
    seen_private, seen_public = set(), set()
    for f in findings:
        for e in EMAIL_RE.findall(str(f.get("value", "")) + " " + str(f.get("excerpt", ""))):
            (seen_private if f.get("method") in PRIVATE_METHODS else seen_public).add(e.lower())
    # anything that also appears in a public-method source is public
    for s in json.loads((example_dir / "sources.json").read_text()) if (example_dir / "sources.json").exists() else []:
        if s.get("tool") in ("web_search", "exa_contents", "fetch_page", "wayback_lookup"):
            p = example_dir / s["path"]
            if p.exists():
                seen_public |= {e.lower() for e in EMAIL_RE.findall(p.read_text())}
    return {e for e in seen_private if e not in seen_public and not e.endswith("users.noreply.github.com")}


def redact_dir(example_dir: Path) -> int:
    emails = private_emails(example_dir)
    if not emails:
        return 0
    mapping = {e: f"redacted:{hashlib.sha256(e.encode()).hexdigest()[:12]}" for e in emails}
    for p in example_dir.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".jsonl", ".md", ".txt"):
            text = p.read_text()
            new = text
            for e, r in mapping.items():
                new = re.sub(re.escape(e), r, new, flags=re.IGNORECASE)
            if new != text:
                p.write_text(new)
    (example_dir / "REDACTED.md").write_text(
        "Recovered private email addresses were replaced by 'redacted:<sha256 prefix>' before commit. "
        f"{len(mapping)} address(es) redacted. Claim content_hash values were computed on the unredacted source files.\n")
    return len(mapping)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(redact_dir(Path(sys.argv[1])))
