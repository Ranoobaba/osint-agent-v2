"""people_search: relatives, ages, past and current cities and addresses as they appear in the search
index snippets of US people-search aggregators (TruePeopleSearch, FastPeopleSearch, ThatsThem,
Spokeo, Whitepages, voterrecords). The sites themselves sit behind Cloudflare and are never fetched;
the snippets are read through Perplexity's domain-filtered search, which is what v1 verified works.
Everything here is sensitive: home addresses and family members. The model records findings with
sensitive=true and attributes them only when the snippet matches the resolved person on name AND a
second marker (age band, city, a relative already known)."""
from __future__ import annotations

import os

from . import RunContext, Tool, ToolResult
from ._http import request_with_retry

PERPLEXITY_SEARCH_URL = "https://api.perplexity.ai/search"
DOMAINS = ["truepeoplesearch.com", "fastpeoplesearch.com", "thatsthem.com", "spokeo.com", "whitepages.com", "voterrecords.com", "radaris.com", "clustrmaps.com"]
PRICE = 0.005


async def _people_search(ctx: RunContext, name: str, city_or_state: str | None = None, age: str | None = None, num_results: int = 10) -> ToolResult:
    name = name.strip()
    if not name:
        return ToolResult(content="people_search needs a name.", error="BadArguments", store_source=False)
    if not ctx.settings.perplexity_api_key:
        return ToolResult(content="people_search unavailable: needs PERPLEXITY_API_KEY (snippets are read through its index).", error="MissingKey", store_source=False)
    q = f'"{name}"' + (f" {city_or_state}" if city_or_state else "") + (f" age {age}" if age else "")
    body = {"query": q, "max_results": max(1, min(int(num_results), 20)), "search_domain_filter": DOMAINS, "search_context_size": "low"}
    try:
        r, _ = await request_with_retry("POST", PERPLEXITY_SEARCH_URL, json=body, headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}", "content-type": "application/json"})
    except Exception as exc:  # noqa: BLE001
        return ToolResult(content=f"people_search error: {type(exc).__name__}", error="HTTPError", cost_usd=PRICE)
    if r.status_code != 200:
        return ToolResult(content=f"people_search HTTP {r.status_code}: {r.text[:200]}", error="HTTPError", cost_usd=PRICE)
    results = r.json().get("results", [])
    lines = [f"# people_search: {q}", f"index snippets from {', '.join(DOMAINS[:4])} and others: {len(results)}", ""]
    for i, x in enumerate(results, 1):
        snippet = " ".join((x.get("snippet") or "").split())
        lines.append(f"{i}. {x.get('title')}\n   url: {x.get('url')}\n   snippet: {snippet[:700]}\n")
    if not results:
        lines.append("Nothing in the people-search index for this name (common for students and non-US residents).")
    lines.append("These aggregators list many same-name people. Attribute a snippet only when it matches on name AND a second marker "
                 "(age band, a city already established, a relative already known). Addresses and relatives are sensitive=true. "
                 "A relative named here is a person lead: record them with field 'relative' and the snippet as evidence.")
    return ToolResult(content="\n".join(lines), cost_usd=PRICE, meta={"result_count": len(results)})


people_search = Tool(
    name="people_search",
    description=("US people-search aggregators through search-index snippets (the sites themselves are walled): relatives and associates, "
                 "age, current and past cities and addresses, phone hints. Use once identity is resolved, with the established city or state "
                 "to narrow. Everything from here is sensitive=true and needs a second marker before attribution. Relatives become person leads."),
    parameters={"type": "object", "properties": {"name": {"type": "string"}, "city_or_state": {"type": "string"}, "age": {"type": "string"},
                                                  "num_results": {"type": "integer", "default": 10}}, "required": ["name"]},
    fn=_people_search, requires=("peoplesearch",),
)
