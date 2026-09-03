"""exa_contents: Exa's cached crawl of a URL. This is the LinkedIn unlock: Exa serves full profile
pages (experience, education, About text) that every direct scraper is walled off from.
livecrawl 'fallback' means the cache is used when present and a live crawl only otherwise."""
from __future__ import annotations

from . import RunContext, Tool, ToolResult
from ._http import request_with_retry

EXA_CONTENTS = "https://api.exa.ai/contents"
EXA_CONTENTS_PRICE = 0.001   # $1 per 1k pages


async def _exa_contents(ctx: RunContext, url: str, max_chars: int = 8000) -> ToolResult:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not ctx.settings.exa_api_key:
        return ToolResult(content="exa_contents unavailable: no EXA_API_KEY.", error="MissingKey", store_source=False)
    max_chars = max(500, min(int(max_chars), 11000))
    try:
        resp, _ = await request_with_retry("POST", EXA_CONTENTS, headers={"x-api-key": ctx.settings.exa_api_key, "content-type": "application/json"},
                                           json={"urls": [url], "text": True, "livecrawl": "fallback"}, timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(content=f"exa_contents error: {type(exc).__name__}", error="HTTPError", cost_usd=EXA_CONTENTS_PRICE)
    if resp.status_code != 200:
        return ToolResult(content=f"exa_contents HTTP {resp.status_code}: {resp.text[:200]}", error="HTTPError", cost_usd=EXA_CONTENTS_PRICE)
    try:
        results = resp.json().get("results") or []
    except ValueError:
        return ToolResult(content="exa_contents returned bad json", error="HTTPError", cost_usd=EXA_CONTENTS_PRICE)
    if not results or not results[0].get("text"):
        return ToolResult(content=f"Exa has no copy of {url} (SOURCE_NOT_AVAILABLE). x.com pages are never served; try another source.",
                          error="NotAvailable", cost_usd=EXA_CONTENTS_PRICE)
    r = results[0]
    head = f"# {r['title']}\n" if r.get("title") else ""
    if r.get("publishedDate"):
        head += f"(Exa index snapshot: {str(r['publishedDate'])[:10]})\n"
    text = head + "\n" + r["text"]
    content = text[:max_chars] + (f"\n\n[truncated: {max_chars} of {len(text)} chars]" if len(text) > max_chars else "")
    return ToolResult(content=content, url=url, cost_usd=EXA_CONTENTS_PRICE, meta={"page_chars": len(text)})


exa_contents = Tool(
    name="exa_contents",
    description=("Read a page from Exa's crawled index. The way to read a LinkedIn profile in full (experience, education, "
                 "About text with emails): find it with web_search(category='linkedin profile'), then pass the URL here. "
                 "Also works for most public pages. x.com pages are not served."),
    parameters={"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "default": 8000}}, "required": ["url"]},
    fn=_exa_contents, requires=("exa",),
)
