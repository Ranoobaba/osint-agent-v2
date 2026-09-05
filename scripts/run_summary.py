"""Summarize a saved run: counts, cost, sweep waves, and findings that look like false attribution.
Usage: uv run python scripts/run_summary.py runs/<name> [runs/<previous name>]"""
import collections
import json
import sys
from pathlib import Path

SUSPECT_KEYS = ("office365", "thegatewaypundit", "twitchtracker")


def load(prefix: str):
    report = json.loads(Path(f"{prefix}_report.json").read_text())
    trace = [json.loads(line) for line in Path(f"{prefix}_trace.jsonl").read_text().splitlines() if line.strip()]
    return report, trace


def main() -> None:
    report, trace = load(sys.argv[1])
    findings = report["findings"]
    run = report.get("run", {})
    print("identity:", report["identity"]["status"], report["identity"].get("name"))
    print("findings:", len(findings), "sensitive:", sum(1 for f in findings if f.get("sensitive")))
    print("run:", {k: run.get(k) for k in ("usd", "llm_usd", "tool_usd", "tool_calls", "steps", "stop_reason", "duration_s") if k in run})
    print("by method:", collections.Counter(f.get("method") for f in findings).most_common())
    print("field prefixes:", collections.Counter(f["field"].split("_")[0] for f in findings).most_common(12))
    src_args = {e["source_id"]: json.dumps(e.get("args")) for e in trace if e.get("span") == "execute_tool" and e.get("source_id")}
    suspect = [f for f in findings if any(k in src_args.get(f.get("source_id"), "") or k in f["value"] or k in f["field"] for k in SUSPECT_KEYS)]
    print("suspect findings (junk keys):", len(suspect))
    for e in trace:
        if e.get("span") == "sweep" and e.get("event") == "end":
            print("sweep:", {k: e.get(k) for k in ("step", "handles", "emails", "domains", "social", "calls", "admitted", "profile_reads")})
        if e.get("span") == "sweep" and e.get("event") == "error":
            print("sweep ERROR:", e.get("error"))
    social = [f for f in findings if f["field"].startswith(("account_facebook", "account_instagram", "family_", "same_surname", "high_school"))]
    for f in social:
        print("  social/family:", f["field"], "=", f["value"][:100])
    rejected = collections.Counter(e.get("reason", "")[:60] for e in trace if e.get("span") == "claim_rejected")
    print("rejections:", rejected.most_common(6))
    if len(sys.argv) > 2:
        prev, _ = load(sys.argv[2])
        before = {(f["field"], f["value"][:60]) for f in prev["findings"]}
        now = {(f["field"], f["value"][:60]) for f in findings}
        print(f"vs {sys.argv[2]}: {len(prev['findings'])} findings before; {len(now - before)} (field,value) pairs new, {len(before - now)} gone")


if __name__ == "__main__":
    main()
