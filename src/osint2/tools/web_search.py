"""web_search: Perplexity Search API and/or Exa search, chosen by the run's TOOLS set. When both are
enabled, a category search goes to Exa (its index has LinkedIn profiles, companies, tweets) and a
domain-filtered or plain search goes to Perplexity. Both render the same text shape. Each call is
charged to the run budget at the provider's list price."""
from __future__ import annotations

import os

from . import RunContext, Tool, ToolResult
from ._http import request_with_retry

PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
EXA_SEARCH_URL = "https://api.exa.ai/search"
PERPLEXITY_PRICE = 0.005   # $5 per 1k requests
EXA_SEARCH_PRICE = 0.005   # $5 per 1k neural searches (contents snippets included)


def _render(query: str, provider: str, results: list[dict]) -> str:
    lines = [f"# web_search ({provider}): {query}", f"results: {len(results)}", ""]
    for i, r in enumerate(results, 1):
        snippet = " ".join((r.get("snippet") or "").split())
        lines.append(f"{i}. {r.get('title') or '(no title)'}")
        lines.append(f"   url: {r.get('url')}")
        if r.get("date"):
            lines.append(f"   date: {str(r['date'])[:10]}")
        if r.get("author"):
            lines.append(f"   author: {r['author']}")
        if snippet:
            lines.append(f"   snippet: {snippet[:700]}")
        lines.append("")
    if not results:
        lines.append("No results. Try a shorter query, drop quotes, or add a distinguishing term (company, city, handle).")
    return "\n".join(lines)


async def _perplexity(query: str, num_results: int, domains: list[str] | None) -> list[dict]:
    body: dict = {"query": query, "max_results": max(1, min(num_results, 20)), "search_context_size": "low"}
    if domains:
        body["search_domain_filter"] = domains[:20]
    response, _ = await request_with_retry("POST", PERPLEXITY_SEARCH_URL, json=body,
                                           headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}", "content-type": "application/json"})
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("snippet"), "date": r.get("date")} for r in data.get("results", [])]


async def _exa(query: str, num_results: int, category: str | None, domains: list[str] | None) -> list[dict]:
    body: dict = {"query": query, "numResults": max(1, min(num_results, 10)), "type": "auto", "contents": {"text": {"maxCharacters": 700}}}
    if category:
        body["category"] = category
    if domains:
        allow = [d for d in domains if not d.startswith("-")]
        deny = [d[1:] for d in domains if d.startswith("-")]
        if allow:
            body["includeDomains"] = allow[:20]
        if deny:
            body["excludeDomains"] = deny[:20]
    response, _ = await request_with_retry("POST", EXA_SEARCH_URL, json=body,
                                           headers={"x-api-key": os.environ["EXA_API_KEY"], "content-type": "application/json"})
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
    data = response.json()
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("text"), "date": r.get("publishedDate"), "author": r.get("author")}
            for r in data.get("results", [])]


async def _web_search(ctx: RunContext, query: str, num_results: int = 8, category: str | None = None,
                      domains: list[str] | None = None) -> ToolResult:
    query = query.strip()
    has_px = "perplexity" in ctx.settings.tools and bool(ctx.settings.perplexity_api_key)
    has_exa = "exa" in ctx.settings.tools and bool(ctx.settings.exa_api_key)
    if not (has_px or has_exa):
        return ToolResult(content="web_search unavailable in this configuration.", error="MissingKey", store_source=False)
    if has_exa and (category or not has_px):
        provider, price = "exa", EXA_SEARCH_PRICE
        runner = _exa(query, int(num_results), category, domains)
    else:
        provider, price = "perplexity", PERPLEXITY_PRICE
        if category:
            query = f"{query} {category}"
        runner = _perplexity(query, int(num_results), domains)
    try:
        results = await runner
    except RuntimeError as exc:
        return ToolResult(content=f"web_search ({provider}) failed: {exc}", error="HTTPError", cost_usd=price, meta={"provider": provider})
    return ToolResult(content=_render(query, provider, results), url=None, cost_usd=price,
                      meta={"provider": provider, "result_count": len(results)})


web_search = Tool(
    name="web_search",
    description=(
        "Search the web. Returns ranked results with title, url, date and a snippet. Use specific queries: the person's "
        "name plus a company, role, handle, city, or a quoted phrase; one fact per query. domains restricts to sites "
        "(e.g. [\"github.com\"]) or excludes with a leading '-'. domains=[\"facebook.com\"] finds public Facebook profiles "
        "via index snippets. category='linkedin profile' (Exa) finds a person's LinkedIn; then exa_contents reads it in full. "
        "A snippet is quotable as a source; a page you have not fetched is not."
    ),
    parameters={"type": "object", "properties": {
        "query": {"type": "string"},
        "num_results": {"type": "integer", "default": 8},
        "domains": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string", "enum": ["people", "company", "news", "github", "research paper", "personal site", "linkedin profile", "tweet", "pdf"],
                     "description": "Exa index categories. 'tweet' finds the person's own posts; 'pdf' finds resumes, CVs, theses and conference PDFs."},
    }, "required": ["query"]},
    fn=_web_search, requires=("perplexity", "exa"),
)
