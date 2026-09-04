"""roblox_lookup: Roblox's public, keyless API. Given a username: user id, display name, profile
description, account creation date, previous usernames (Roblox keeps the history public), friend,
follower and following counts, and games the account created. Old usernames are a real pivot: people
reuse them elsewhere. Gaming presence is personal; findings from here are marked sensitive by the
model per the prompt rule."""
from __future__ import annotations

import asyncio
from typing import Any

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

USERS = "https://users.roblox.com/v1"
FRIENDS = "https://friends.roblox.com/v1"
GAMES = "https://games.roblox.com/v2"


async def _json(method: str, url: str, **kw: Any) -> Any:
    r, _ = await request_with_retry(method, url, headers={"User-Agent": UA, "accept": "application/json"}, timeout=20.0, **kw)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {url.split('/v')[0]}")
    return r.json()


async def _roblox_lookup(ctx: RunContext, username: str) -> ToolResult:
    username = username.strip().lstrip("@")
    if not username:
        return ToolResult(content="roblox_lookup needs a username.", error="BadArguments", store_source=False)
    try:
        data = await _json("POST", f"{USERS}/usernames/users", json={"usernames": [username], "excludeBannedUsers": False})
    except RuntimeError as exc:
        return ToolResult(content=f"roblox_lookup failed: {exc}", error="HTTPError")
    rows = data.get("data") or []
    url = f"https://www.roblox.com/search/users?keyword={username}"
    if not rows:
        return ToolResult(content=f"# roblox_lookup: {username}\nNo Roblox account with this exact username.", url=url, meta={"found": False})
    uid = rows[0]["id"]
    url = f"https://www.roblox.com/users/{uid}/profile"
    prof, hist, fr, fo, fi, games = await asyncio.gather(
        _json("GET", f"{USERS}/users/{uid}"),
        _json("GET", f"{USERS}/users/{uid}/username-history?limit=50&sortOrder=Desc"),
        _json("GET", f"{FRIENDS}/users/{uid}/friends/count"),
        _json("GET", f"{FRIENDS}/users/{uid}/followers/count"),
        _json("GET", f"{FRIENDS}/users/{uid}/followings/count"),
        _json("GET", f"{GAMES}/users/{uid}/games?limit=10&sortOrder=Desc"),
        return_exceptions=True)
    def ok(x: Any) -> Any:
        return None if isinstance(x, Exception) else x
    prof, hist, fr, fo, fi, games = map(ok, (prof, hist, fr, fo, fi, games))
    lines = [f"# roblox_lookup: {username}", f"user id: {uid}  profile: {url}"]
    if prof:
        lines.append(f"display name: {prof.get('displayName')}  created: {str(prof.get('created'))[:10]}  banned: {prof.get('isBanned')}  verified badge: {prof.get('hasVerifiedBadge')}")
        if prof.get("description"):
            lines.append("description: " + " ".join(str(prof["description"]).split())[:600])
    prev = [h.get("name") for h in (hist or {}).get("data", []) if h.get("name")]
    lines.append("previous usernames: " + (", ".join(prev) if prev else "none on record"))
    lines.append(f"friends: {(fr or {}).get('count')}  followers: {(fo or {}).get('count')}  following: {(fi or {}).get('count')}")
    gl = (games or {}).get("data", [])
    if gl:
        lines.append(f"games created ({len(gl)}):")
        for g in gl[:10]:
            lines.append(f"  - {g.get('name')}  visits={g.get('placeVisits')}  created={str(g.get('created'))[:10]}  https://www.roblox.com/games/{g.get('rootPlace', {}).get('id') if isinstance(g.get('rootPlace'), dict) else ''}")
    lines.append("\nA matching username is not proof it is the same person; confirm with the description, a linked handle, or a shared previous username. Mark findings sensitive.")
    return ToolResult(content="\n".join(lines), url=url, meta={"found": True, "user_id": uid, "previous_usernames": len(prev), "games": len(gl)})


roblox_lookup = Tool(
    name="roblox_lookup",
    description=("Roblox public account lookup by exact username: display name, profile description, account creation date, previous "
                 "usernames (public history, a pivot to other platforms), friend and follower counts, games created. Use it on the target's "
                 "confirmed handles and on any old handles you recover. Gaming presence is personal: mark findings sensitive."),
    parameters={"type": "object", "properties": {"username": {"type": "string"}}, "required": ["username"]},
    fn=_roblox_lookup, requires=("roblox",),
)
