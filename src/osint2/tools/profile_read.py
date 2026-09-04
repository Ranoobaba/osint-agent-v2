"""profile_read: keyless JSON endpoints for platforms a username sweep flags but no page fetcher can
read well. reddit (about + recent comments: self-disclosed school, city, age), dockerhub (full name,
location, company, joined), hackernews (about, karma, created, recent comments), keybase (proven links
between GitHub, Twitter, Reddit and domains: a hard identity key), chess.com and lichess (name,
location, joined). One call, one platform, one handle."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

PLATFORMS = ("reddit", "dockerhub", "hackernews", "keybase", "chesscom", "lichess")


async def _get(url: str, **kw):
    r, _ = await request_with_retry("GET", url, headers={"User-Agent": "osint-agent-v2/1.0 (research; contact via repo)", "accept": "application/json"}, timeout=20.0, **kw)
    return r


def _ts(v) -> str:
    try:
        return datetime.fromtimestamp(float(v), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return str(v)


async def _profile_read(ctx: RunContext, platform: str, handle: str) -> ToolResult:
    platform = platform.strip().lower(); handle = handle.strip().lstrip("@")
    if platform not in PLATFORMS or not handle:
        return ToolResult(content=f"profile_read needs platform in {PLATFORMS} and a handle.", error="BadArguments", store_source=False)
    lines = [f"# profile_read: {platform} {handle}"]
    try:
        if platform == "reddit":
            url = f"https://www.reddit.com/user/{handle}"
            a = await _get(f"{url}/about.json")
            if a.status_code != 200:
                return ToolResult(content=f"{lines[0]}\nreddit HTTP {a.status_code}: no such user or blocked.", url=url, error=None if a.status_code == 404 else "HTTPError")
            d = a.json().get("data", {})
            lines.append(f"profile: {url}  created: {_ts(d.get('created_utc'))}  link karma: {d.get('link_karma')}  comment karma: {d.get('comment_karma')}  verified: {d.get('verified')}")
            if (d.get("subreddit") or {}).get("public_description"):
                lines.append("bio: " + " ".join(d["subreddit"]["public_description"].split())[:300])
            c = await _get(f"{url}/comments.json", params={"limit": 40})
            if c.status_code == 200:
                subs: dict[str, int] = {}
                for ch in c.json().get("data", {}).get("children", []):
                    x = ch.get("data", {}); subs[x.get("subreddit", "?")] = subs.get(x.get("subreddit", "?"), 0) + 1
                    body = " ".join((x.get("body") or "").split())
                    if len(body) > 60:
                        lines.append(f"  - r/{x.get('subreddit')} {_ts(x.get('created_utc'))}: {body[:240]}")
                lines.insert(2, "subreddits: " + ", ".join(f"{k} x{v}" for k, v in sorted(subs.items(), key=lambda kv: -kv[1])[:12]))
        elif platform == "dockerhub":
            url = f"https://hub.docker.com/u/{handle}"
            r = await _get(f"https://hub.docker.com/v2/users/{handle}/")
            if r.status_code != 200:
                return ToolResult(content=f"{lines[0]}\ndocker hub HTTP {r.status_code}: no such user.", url=url)
            d = r.json()
            lines.append(f"profile: {url}  full name: {d.get('full_name')!r}  location: {d.get('location')!r}  company: {d.get('company')!r}  joined: {str(d.get('date_joined'))[:10]}  type: {d.get('type')}")
            if d.get("profile_url"):
                lines.append(f"linked site: {d['profile_url']}")
        elif platform == "hackernews":
            url = f"https://news.ycombinator.com/user?id={handle}"
            r = await _get(f"https://hacker-news.firebaseio.com/v0/user/{handle}.json")
            d = r.json() if r.status_code == 200 else None
            if not d:
                return ToolResult(content=f"{lines[0]}\nno Hacker News user {handle}.", url=url)
            lines.append(f"profile: {url}  created: {_ts(d.get('created'))}  karma: {d.get('karma')}")
            if d.get("about"):
                lines.append("about: " + " ".join(str(d["about"]).split())[:400])
            s = await _get("https://hn.algolia.com/api/v1/search", params={"tags": f"comment,author_{handle}", "hitsPerPage": 25})
            if s.status_code == 200:
                for h in s.json().get("hits", []):
                    txt = " ".join((h.get("comment_text") or "").replace("<p>", " ").split())
                    if len(txt) > 60:
                        lines.append(f"  - {str(h.get('created_at'))[:10]}: {txt[:240]}")
        elif platform == "keybase":
            url = f"https://keybase.io/{handle}"
            r = await _get("https://keybase.io/_/api/1.0/user/lookup.json", params={"usernames": handle, "fields": "proofs_summary,basics,profile"})
            them = (r.json().get("them") or [None])[0] if r.status_code == 200 else None
            if not them:
                return ToolResult(content=f"{lines[0]}\nno Keybase user {handle}.", url=url)
            prof = them.get("profile") or {}
            lines.append(f"profile: {url}  full name: {prof.get('full_name')!r}  location: {prof.get('location')!r}  bio: {' '.join(str(prof.get('bio') or '').split())[:200]!r}")
            for pr in (them.get("proofs_summary") or {}).get("all", []):
                lines.append(f"  proven: {pr.get('proof_type')} {pr.get('nametag')}  {pr.get('service_url') or pr.get('proof_url')}")
        elif platform in ("chesscom", "lichess"):
            if platform == "chesscom":
                url = f"https://www.chess.com/member/{handle}"
                r = await _get(f"https://api.chess.com/pub/player/{handle}")
            else:
                url = f"https://lichess.org/@/{handle}"
                r = await _get(f"https://lichess.org/api/user/{handle}")
            if r.status_code != 200:
                return ToolResult(content=f"{lines[0]}\n{platform} HTTP {r.status_code}: no such player.", url=url)
            d = r.json(); p = d.get("profile") or {}
            lines.append(f"profile: {url}  name: {d.get('name') or (p.get('firstName', '') + ' ' + p.get('lastName', '')).strip()!r}  "
                         f"location: {d.get('location') or p.get('location')!r}  country: {d.get('country') or p.get('country')!r}  joined: {_ts(d.get('joined')) if d.get('joined') else str(d.get('createdAt', ''))[:10]}")
            if p.get("bio"):
                lines.append("bio: " + " ".join(str(p["bio"]).split())[:300])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(content=f"profile_read error: {type(exc).__name__}", error="HTTPError")
    lines.append("\nA matching handle is a lead, not proof: confirm with bio, name, location or a proven link before attributing. Personal-life content is sensitive.")
    return ToolResult(content="\n".join(lines), url=url, meta={"platform": platform})


profile_read = Tool(
    name="profile_read",
    description=("Read a public account through its keyless JSON endpoint: reddit (bio, subreddits, recent comments), dockerhub (full name, "
                 "location, company), hackernews (about, comments), keybase (cryptographically proven links between GitHub, Twitter, Reddit "
                 "and domains), chesscom, lichess. Use it on handles a whatsmyname sweep flags on these platforms, right after the sweep."),
    parameters={"type": "object", "properties": {"platform": {"type": "string", "enum": list(PLATFORMS)}, "handle": {"type": "string"}}, "required": ["platform", "handle"]},
    fn=_profile_read, requires=("profiles",),
)
