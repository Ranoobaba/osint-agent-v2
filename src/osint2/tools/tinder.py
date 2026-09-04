"""tinder_check: Tinder web profiles at tinder.com/@username exist only when the account holder has
turned the public profile on, so a hit is opt-in public information. The page embeds the profile as
JSON (window.__data.webProfile). Returns name, age, bio, schools, jobs and photo count when present.
Dating presence is sensitive by default; findings from here are marked sensitive."""
from __future__ import annotations

import json
import re
from datetime import date

from . import RunContext, Tool, ToolResult
from ._http import request_with_retry

DATA_RE = re.compile(r"window\.__data\s*=\s*(\{.*?\})\s*;\s*</script>", re.S)


def _age(birth: str | None) -> int | None:
    if not birth:
        return None
    try:
        y, m, d = int(birth[:4]), int(birth[5:7]), int(birth[8:10])
        t = date.today()
        return t.year - y - ((t.month, t.day) < (m, d))
    except ValueError:
        return None


async def _tinder_check(ctx: RunContext, username: str) -> ToolResult:
    username = username.strip().lstrip("@")
    if not username:
        return ToolResult(content="tinder_check needs a username.", error="BadArguments", store_source=False)
    url = f"https://tinder.com/@{username}"
    try:
        r, _ = await request_with_retry("GET", url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                                              "accept": "text/html"}, timeout=25.0)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(content=f"tinder_check error: {type(exc).__name__}", error="HTTPError")
    if r.status_code == 404:
        return ToolResult(content=f"# tinder_check: {username}\nNo public Tinder web profile at {url}.", url=url, meta={"found": False})
    if r.status_code != 200:
        return ToolResult(content=f"tinder_check HTTP {r.status_code}", error="HTTPError")
    m = DATA_RE.search(r.text)
    prof = None
    if m:
        try:
            data = json.loads(m.group(1))
            prof = (data.get("webProfile") or {}).get("user") or None
        except ValueError:
            prof = None
    if not prof or not prof.get("name"):
        return ToolResult(content=f"# tinder_check: {username}\nNo public Tinder web profile for this username (the page exists but carries no profile; the user has not enabled a web profile, or the handle is unused).", url=url, meta={"found": False})
    schools = [s.get("name") for s in prof.get("schools") or [] if s.get("name")]
    jobs = [" at ".join(x for x in [(j.get("title") or {}).get("name"), (j.get("company") or {}).get("name")] if x) for j in prof.get("jobs") or []]
    lines = [f"# tinder_check: {username}", f"public web profile: {url}",
             f"name: {prof.get('name')}  age: {_age(prof.get('birth_date'))}  gender: {prof.get('gender')}",
             f"bio: {' '.join(str(prof.get('bio') or '').split())[:500]}"]
    if schools:
        lines.append("schools: " + "; ".join(schools))
    if jobs:
        lines.append("jobs: " + "; ".join(j for j in jobs if j))
    lines.append(f"photos: {len(prof.get('photos') or [])}")
    lines.append("\nOpt-in public profile. Confirm it is the same person by name, age, school or job before recording; mark findings sensitive.")
    return ToolResult(content="\n".join(lines), url=url, meta={"found": True, "schools": len(schools), "jobs": len(jobs)})


tinder_check = Tool(
    name="tinder_check",
    description=("Check whether a username has an opt-in public Tinder web profile (tinder.com/@username) and read it: name, age, bio, schools, "
                 "jobs, photo count. Use on the target's confirmed handles. A hit is public by the holder's choice, but dating presence is "
                 "personal: confirm identity by name, age, school or job, and mark findings sensitive."),
    parameters={"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]},
    fn=_tinder_check, requires=("tinder",),
)
