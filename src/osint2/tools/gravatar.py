"""gravatar_lookup: an email's SHA-256 is a public key into Gravatar's profile directory. Returns the
profile fields and the hash, which is a hard identity key across tools. Salvaged from v1."""
from __future__ import annotations

import hashlib
import os
from typing import Any

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

PROFILE_API = "https://api.gravatar.com/v3/profiles/{hash}"
PROFILE_JSON = "https://gravatar.com/{hash}.json"
AVATAR = "https://gravatar.com/avatar/{hash}?d=404&s=200"


def email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


async def _gravatar_lookup(ctx: RunContext, email: str) -> ToolResult:
    email = email.strip().lower()
    if "@" not in email:
        return ToolResult(content="gravatar_lookup needs an email address.", error="BadArguments")
    h = email_hash(email)
    headers = {"User-Agent": UA, "Accept": "application/json"}
    key = os.environ.get("GRAVATAR_API_KEY", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    profile: dict[str, Any] | None = None
    source = None
    response, _ = await request_with_retry("GET", PROFILE_API.format(hash=h), headers=headers, timeout=20.0)
    if response.status_code == 200:
        profile, source = response.json(), "api_v3"
    elif response.status_code != 404:
        response2, _ = await request_with_retry("GET", PROFILE_JSON.format(hash=h), headers={"User-Agent": UA}, timeout=20.0)
        if response2.status_code == 200:
            profile, source = (response2.json().get("entry") or [{}])[0], "legacy_json"
    avatar_resp, _ = await request_with_retry("HEAD", AVATAR.format(hash=h), headers={"User-Agent": UA}, timeout=15.0)
    has_avatar = avatar_resp.status_code == 200
    url = f"https://gravatar.com/{h}"
    lines = [f"# gravatar_lookup: {email}", f"sha256: {h}", f"avatar: {'yes ' + AVATAR.format(hash=h) if has_avatar else 'none'}", ""]
    if not profile:
        lines.append("No public Gravatar profile for this email (that is common; not an error).")
        return ToolResult(content="\n".join(lines), url=url, meta={"found": False, "has_avatar": has_avatar})
    if source == "api_v3":
        fields = {k: profile.get(k) for k in ("display_name", "first_name", "last_name", "location", "job_title", "company", "description", "profile_url", "avatar_url", "pronouns")}
        verified = [{"service": a.get("service_label") or a.get("service_type"), "url": a.get("url")} for a in profile.get("verified_accounts") or []]
        links = [{"label": lk.get("label"), "url": lk.get("url")} for lk in profile.get("links") or []]
    else:
        fields = {"display_name": profile.get("displayName"), "location": profile.get("currentLocation"), "description": profile.get("aboutMe"),
                  "profile_url": profile.get("profileUrl"), "avatar_url": profile.get("thumbnailUrl")}
        verified = [{"service": a.get("shortname"), "url": a.get("url")} for a in profile.get("accounts") or []]
        links = [{"label": u.get("title"), "url": u.get("value")} for u in profile.get("urls") or []]
    lines.append(f"profile ({source}): " + ", ".join(f"{k}={v!r}" for k, v in fields.items() if v))
    if verified:
        lines.append("verified accounts:")
        lines += [f"  - {a['service']}: {a['url']}" for a in verified]
    if links:
        lines.append("links:")
        lines += [f"  - {lk['label'] or ''} {lk['url']}" for lk in links]
    lines.append("")
    lines.append("Next: record_candidate with these fields (avatar_hash = the sha256 above); verified accounts are strong identity markers.")
    return ToolResult(content="\n".join(lines), url=fields.get("profile_url") or url,
                      meta={"found": True, "has_avatar": has_avatar, "verified_accounts": len(verified)})


gravatar_lookup = Tool(
    name="gravatar_lookup",
    description=("Look up the public Gravatar profile for an email address (hashed client-side): display name, location, job title, "
                 "company, verified social accounts and links, plus whether an avatar exists. Call it on every real email recovered "
                 "by github_intel or given as the target. The hash is a hard identity key for record_candidate's avatar_hash."),
    parameters={"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]},
    fn=_gravatar_lookup, requires=("gravatar",),
)
