"""wayback_lookup: digital archaeology through the Internet Archive's CDX index. Lists what was ever
captured under a URL prefix, shows the capture timeline of one page, or reads an archived snapshot
(raw fetch, HTML stripped; no Jina). Salvaged from v1."""
from __future__ import annotations

import re
from html import unescape

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

CDX = "https://web.archive.org/cdx/search/cdx"
SNAPSHOT = "https://web.archive.org/web/{ts}id_/{url}"


def _clean_url(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


async def _cdx(params: dict) -> list[list[str]]:
    response, _ = await request_with_retry("GET", CDX, params=params, timeout=45.0, headers={"User-Agent": UA})
    if response.status_code != 200:
        raise RuntimeError(f"CDX HTTP {response.status_code}: {response.text[:200]}")
    try:
        rows = response.json()
    except ValueError:
        rows = []
    return rows[1:] if rows else []


async def _wayback_lookup(ctx: RunContext, url: str, mode: str = "list", timestamp: str | None = None,
                          from_date: str | None = None, to_date: str | None = None, limit: int = 40, max_chars: int = 6000) -> ToolResult:
    target = _clean_url(url)
    if not target:
        return ToolResult(content="wayback_lookup needs a url.", error="BadArguments")
    limit = max(1, min(int(limit), 200))
    mode = (mode or "list").lower()
    base = {"output": "json", "filter": "statuscode:200"}
    if from_date:
        base["from"] = re.sub(r"\D", "", from_date)
    if to_date:
        base["to"] = re.sub(r"\D", "", to_date)
    try:
        if mode == "list":
            rows = await _cdx({**base, "url": target + "/*", "matchType": "prefix", "collapse": "urlkey", "fl": "timestamp,original,mimetype", "limit": limit})
            root_rows = await _cdx({**base, "url": target, "fl": "timestamp,original,mimetype", "limit": 1})
            if root_rows:
                rows = root_rows + [r for r in rows if r[1].rstrip("/") != root_rows[0][1].rstrip("/")]
            lines = [f"# wayback_lookup list: {target}", f"unique archived URLs: {len(rows)} (limit {limit})", ""]
            for ts, orig, mime in rows:
                lines.append(f"- {ts[:4]}-{ts[4:6]}-{ts[6:8]}  {orig}  [{mime}]")
            if not rows:
                lines.append("Nothing archived under this URL. Try the bare domain, an older domain, or a profile URL.")
            else:
                lines.append("\nNext: mode='snapshots' for one URL's timeline, or mode='read' with a timestamp to read an old version.")
            return ToolResult(content="\n".join(lines), url=f"https://web.archive.org/web/*/{target}/*", meta={"mode": mode, "captures": len(rows)})
        if mode == "snapshots":
            rows = await _cdx({**base, "url": target, "fl": "timestamp,original,digest", "collapse": "timestamp:6", "limit": limit})
            lines = [f"# wayback_lookup snapshots: {target}", f"captures (one per month, content-changed marked *): {len(rows)}", ""]
            prev = None
            for ts, orig, digest in rows:
                lines.append(f"{'*' if digest != prev else ' '} {ts}  {ts[:4]}-{ts[4:6]}-{ts[6:8]}")
                prev = digest
            lines.append(f"\noldest: {rows[0][0]}  newest: {rows[-1][0]}. Read one with mode='read', timestamp=<14 digits>." if rows else "No captures of this exact URL.")
            return ToolResult(content="\n".join(lines), url=f"https://web.archive.org/web/*/{target}", meta={"mode": mode, "captures": len(rows)})
        if mode == "read":
            if not timestamp:
                rows = await _cdx({**base, "url": target, "fl": "timestamp", "limit": 1})
                if not rows:
                    return ToolResult(content=f"No archived capture of {target}.", meta={"mode": mode, "captures": 0}, store_source=False)
                timestamp = rows[0][0]
            ts = re.sub(r"\D", "", timestamp)[:14].ljust(14, "0")
            snap = SNAPSHOT.format(ts=ts, url="https://" + target)
            r, _ = await request_with_retry("GET", snap, timeout=60.0, headers={"User-Agent": UA})
            if r.status_code != 200:
                return ToolResult(content=f"Snapshot {snap} returned HTTP {r.status_code}.", error=f"HTTP{r.status_code}")
            text = _strip_html(r.text) if "html" in r.headers.get("content-type", "") else r.text
            max_chars = max(500, min(int(max_chars), 11000))
            lines = [f"# wayback_lookup read: {target} @ {ts[:4]}-{ts[4:6]}-{ts[6:8]}  ({snap})", "", text[:max_chars]]
            if len(text) > max_chars:
                lines.append(f"\n[truncated: {max_chars} of {len(text)} chars]")
            return ToolResult(content="\n".join(lines), url=snap, meta={"mode": mode, "timestamp": ts, "chars": len(text)})
        return ToolResult(content="mode must be list, snapshots, or read.", error="BadArguments")
    except RuntimeError as exc:
        return ToolResult(content=f"wayback_lookup failed: {exc}", error="HTTPError", meta={"mode": mode})


wayback_lookup = Tool(
    name="wayback_lookup",
    description=("Internet Archive digital archaeology. mode='list': every unique URL ever archived under a domain or path (old personal "
                 "sites, dead startup pages). mode='snapshots': the capture timeline of one URL. mode='read': the text of an archived "
                 "version (oldest by default, or a 14-digit timestamp). Use it on a personal domain, an old company site, or a profile URL "
                 "to recover earlier bios, handles, employers and projects. The snapshot URL it returns is the source to cite."),
    parameters={"type": "object", "properties": {
        "url": {"type": "string"}, "mode": {"type": "string", "enum": ["list", "snapshots", "read"], "default": "list"},
        "timestamp": {"type": "string", "description": "For read: YYYYMMDD or 14 digits. Default oldest."},
        "from_date": {"type": "string"}, "to_date": {"type": "string"},
        "limit": {"type": "integer", "default": 40}, "max_chars": {"type": "integer", "default": 6000},
    }, "required": ["url"]},
    fn=_wayback_lookup, requires=("wayback",),
)
