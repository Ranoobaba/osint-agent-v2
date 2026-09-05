"""Run one investigation through the deployed endpoint and save report + trace under runs/<name>_*.
Usage: uv run python scripts/live_run.py "<target>" <name> [max_tool_calls]"""
import json, os, sys, time, pathlib
import httpx
from dotenv import load_dotenv

load_dotenv()
BASE = os.environ.get("APP_URL", "https://ranoobaba--osint-agent-v2-web.modal.run")
target, name = sys.argv[1], sys.argv[2]
calls = int(sys.argv[3]) if len(sys.argv) > 3 else 40
h = {"x-api-key": os.environ["AGENT_API_KEY"]}
r = httpx.post(f"{BASE}/investigate", json={"target": target, "max_tool_calls": calls}, headers=h, timeout=60)
r.raise_for_status()
job = r.json()["job_id"]
print("job", job, flush=True)
t0 = time.time()
while True:
    time.sleep(15)
    j = httpx.get(f"{BASE}/jobs/{job}", headers=h, timeout=60).json()
    p = j.get("partial") or {}
    print(f"{int(time.time()-t0)}s {j['status']} step={p.get('step')} calls={p.get('tool_calls')} admitted={p.get('admitted')} usd={p.get('usd')} last={p.get('last_tool')}", flush=True)
    if j["status"] in ("done", "failed"):
        break
out = pathlib.Path("runs"); out.mkdir(exist_ok=True)
(out / f"{name}.json").write_text(json.dumps(j, indent=2))
if j["status"] == "done":
    (out / f"{name}_report.json").write_text(json.dumps(j["report"], indent=2))
    tr = httpx.get(f"{BASE}/jobs/{job}/trace", headers=h, timeout=120)
    (out / f"{name}_trace.jsonl").write_bytes(tr.content)
    rep = j["report"]
    print("findings", len(rep.get("findings", [])), "cost", rep.get("run", {}).get("usd"), "identity", rep.get("identity", {}).get("status"))
else:
    print("FAILED", j.get("error"))
