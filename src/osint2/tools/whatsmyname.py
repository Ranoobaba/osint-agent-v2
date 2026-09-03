"""whatsmyname: username enumeration with the community WhatsMyName dataset (700+ sites, per-site
existence strings, few false positives). Time-capped and concurrency-limited. Salvaged from v1."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from . import RunContext, Tool, ToolResult

WMN_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
TOTAL_TIMEOUT = 50.0
PER_SITE_TIMEOUT = 8.0
CONCURRENCY = 25
_CACHE: dict[str, Any] = {}


async def _load_sites() -> list[dict[str, Any]]:
    if "sites" in _CACHE:
        return _CACHE["sites"]
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(WMN_URL, headers={"User-Agent": "osint-agent-v2"})
    sites = r.json().get("sites", []) if r.status_code == 200 else []
    _CACHE["sites"] = [s for s in sites if s.get("uri_check")]
    return _CACHE["sites"]


async def _check(client: httpx.AsyncClient, site: dict[str, Any], username: str, sem: asyncio.Semaphore) -> dict[str, Any] | None:
    uri = str(site["uri_check"]).replace("{account}", username)
    try:
        async with sem:
            r = await client.get(uri, timeout=PER_SITE_TIMEOUT, headers={"User-Agent": "Mozilla/5.0 osint-agent-v2"})
    except Exception:  # noqa: BLE001
        return None
    e_code, e_str, m_code, m_str = site.get("e_code"), site.get("e_string"), site.get("m_code"), site.get("m_string")
    if e_code is not None and r.status_code != e_code:
        return None
    if e_str and e_str not in r.text:
        return None
    if m_str and m_str in r.text:
        return None
    if m_code is not None and r.status_code == m_code and e_code is None:
        return None
    return {"site": site.get("name"), "category": site.get("cat"), "url": uri}


async def _whatsmyname(ctx: RunContext, username: str, categories: list[str] | None = None) -> ToolResult:
    username = username.strip().lstrip("@")
    if not username:
        return ToolResult(content="whatsmyname needs a username.", error="BadArguments")
    sites = await _load_sites()
    if not sites:
        return ToolResult(content="whatsmyname unavailable: could not load the WhatsMyName dataset.", error="Unavailable")
    if categories:
        cats = {c.lower() for c in categories}
        sites = [s for s in sites if str(s.get("cat", "")).lower() in cats]
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [asyncio.ensure_future(_check(client, s, username, sem)) for s in sites]
        done, pending = await asyncio.wait(tasks, timeout=TOTAL_TIMEOUT)
        for t in pending:
            t.cancel()
        results = [t.result() for t in done if not t.cancelled() and t.exception() is None]
    hits = [r for r in results if isinstance(r, dict)]
    lines = [f"# whatsmyname: {username}", f"checked {len(sites)} curated sites ({len(pending)} timed out), found on {len(hits)}", ""]
    by_cat: dict[str, list[str]] = {}
    for h in hits:
        by_cat.setdefault(h.get("category") or "other", []).append(f"{h['site']}: {h['url']}")
    for cat in sorted(by_cat):
        lines.append(f"[{cat}]")
        lines += [f"  - {x}" for x in sorted(by_cat[cat])]
    if not hits:
        lines.append("No accounts found under this username in the curated set.")
    lines.append("\nHigh-precision existence hits. Confirm identity by bio or avatar before attributing; each hit is a lead to pivot on.")
    return ToolResult(content="\n".join(lines), url=f"https://whatsmyname.app/?q={username}",
                      meta={"checked": len(sites), "hits": len(hits), "timed_out": len(pending)})


whatsmyname = Tool(
    name="whatsmyname",
    description=("Check a username across 700+ curated sites (the WhatsMyName dataset) with per-site existence rules. Returns the sites "
                 "the handle exists on, grouped by category. Use it on a confirmed handle. Takes up to ~50s. Confirm each hit by bio or avatar."),
    parameters={"type": "object", "properties": {
        "username": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}, "description": "Optional category filter, e.g. 'coding', 'social'."},
    }, "required": ["username"]},
    fn=_whatsmyname, requires=("whatsmyname",),
)
