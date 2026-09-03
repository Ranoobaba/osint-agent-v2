"""fetch_page: Firecrawl renders a URL (JavaScript included) into main-content markdown. Login-walled
social hosts are refused up front with a pointer to exa_contents, so the model does not burn calls on
walls. No Jina."""
from __future__ import annotations

from . import RunContext, Tool, ToolResult
from ._http import request_with_retry

FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v1/scrape"
FIRECRAWL_PRICE = 0.002   # about 1 credit per page on the standard plan
WALLED_HOSTS = ("linkedin.com", "x.com", "twitter.com", "instagram.com", "facebook.com", "threads.net")


async def _fetch_page(ctx: RunContext, url: str, max_chars: int = 8000) -> ToolResult:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    max_chars = max(500, min(int(max_chars), 11000))
    host = url.lower().split("/", 3)[2].removeprefix("www.") if "://" in url else ""
    if any(host == h or host.endswith("." + h) for h in WALLED_HOSTS):
        hint = "use exa_contents on this URL" if "exa" in ctx.settings.tools else "this configuration has no way to read it; do not retry"
        return ToolResult(content=f"fetch_page cannot read {url}: {host} serves a login wall to scrapers; {hint}.",
                          error="LoginWall", store_source=False)
    if not ctx.settings.firecrawl_api_key:
        return ToolResult(content="fetch_page unavailable: no FIRECRAWL_API_KEY.", error="MissingKey", store_source=False)
    try:
        resp, _ = await request_with_retry("POST", FIRECRAWL_SCRAPE, headers={"Authorization": f"Bearer {ctx.settings.firecrawl_api_key}", "Content-Type": "application/json"},
                                           json={"url": url, "formats": ["markdown"], "onlyMainContent": True}, timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(content=f"fetch_page error: {type(exc).__name__}", error="HTTPError", cost_usd=FIRECRAWL_PRICE)
    if resp.status_code != 200:
        return ToolResult(content=f"fetch_page HTTP {resp.status_code}: {resp.text[:200]}", error="HTTPError", cost_usd=FIRECRAWL_PRICE)
    try:
        md = (resp.json().get("data") or {}).get("markdown")
    except ValueError:
        md = None
    if not md:
        return ToolResult(content=f"fetch_page got an empty page for {url}.", error="Empty", cost_usd=FIRECRAWL_PRICE)
    content = md[:max_chars] + (f"\n\n[truncated: {max_chars} of {len(md)} chars]" if len(md) > max_chars else "")
    return ToolResult(content=content, url=url, cost_usd=FIRECRAWL_PRICE, meta={"page_chars": len(md)})


fetch_page = Tool(
    name="fetch_page",
    description=("Fetch a web page and return its main content as markdown (renders JavaScript). Use it to read a search result in "
                 "full: personal sites, company pages, bios, articles, GitHub pages. LinkedIn, X, Instagram and Facebook are walled; "
                 "read LinkedIn through exa_contents instead. A page fetched once this run is cached; do not re-fetch it."),
    parameters={"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer", "default": 8000}}, "required": ["url"]},
    fn=_fetch_page, requires=("firecrawl",),
)
