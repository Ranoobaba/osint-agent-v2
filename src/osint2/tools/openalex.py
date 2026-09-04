"""openalex_lookup: publications, co-authors and affiliations from OpenAlex, a free keyless index of
scholarly works. Given a name (and an optional affiliation word) it lists matching author records with
their institutions, work counts and top works with co-author names. High yield for anyone with a
research footprint; empty for everyone else, and it says so."""
from __future__ import annotations

from typing import Any

from . import RunContext, Tool, ToolResult
from ._http import UA, request_with_retry

AUTHORS = "https://api.openalex.org/authors"
WORKS = "https://api.openalex.org/works"
MAILTO = "osint-agent-v2@example.com"   # OpenAlex polite pool; any address works


async def _get(url: str, **params: Any) -> Any:
    params["mailto"] = MAILTO
    r, _ = await request_with_retry("GET", url, params=params, headers={"User-Agent": UA}, timeout=30.0)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAlex HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def _openalex_lookup(ctx: RunContext, name: str, affiliation: str | None = None, max_authors: int = 3, max_works: int = 6) -> ToolResult:
    name = name.strip()
    if not name:
        return ToolResult(content="openalex_lookup needs a name.", error="BadArguments", store_source=False)
    try:
        data = await _get(AUTHORS, search=name, per_page=10)
    except RuntimeError as exc:
        return ToolResult(content=f"openalex_lookup failed: {exc}", error="HTTPError")
    authors = data.get("results", [])
    if affiliation:
        a = affiliation.lower()
        ranked = sorted(authors, key=lambda x: (not any(a in (i.get("display_name") or "").lower() for i in (x.get("affiliations") or []) for i in [i.get("institution") or {}]), -(x.get("works_count") or 0)))
    else:
        ranked = sorted(authors, key=lambda x: -(x.get("works_count") or 0))
    ranked = ranked[:max(1, min(int(max_authors), 5))]
    lines = [f"# openalex_lookup: {name}" + (f" (affiliation filter: {affiliation})" if affiliation else ""), f"author records matching: {len(authors)}", ""]
    if not authors:
        lines.append("No author record. The person has no indexed publications under this name (common; not an error).")
        return ToolResult(content="\n".join(lines), url=f"https://openalex.org/authors?search={name}", meta={"authors": 0})
    total_works = 0
    for a in ranked:
        insts = []
        for aff in a.get("affiliations") or []:
            inst = (aff.get("institution") or {}).get("display_name")
            years = aff.get("years") or []
            if inst:
                insts.append(f"{inst} ({min(years)}-{max(years)})" if years else inst)
        lines.append(f"## {a.get('display_name')}  works={a.get('works_count')} cited_by={a.get('cited_by_count')}  {a.get('id')}")
        if insts:
            lines.append("affiliations: " + "; ".join(insts[:5]))
        orcid = a.get("orcid")
        if orcid:
            lines.append(f"orcid: {orcid}")
        try:
            works = await _get(WORKS, filter=f"author.id:{a['id'].rsplit('/', 1)[-1]}", sort="publication_year:desc", per_page=max(1, min(int(max_works), 10)))
        except RuntimeError:
            works = {"results": []}
        for w in works.get("results", []):
            total_works += 1
            coauthors = [x.get("author", {}).get("display_name") for x in w.get("authorships", []) if x.get("author", {}).get("display_name") and x.get("author", {}).get("display_name") != a.get("display_name")]
            venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
            lines.append(f"  - {w.get('publication_year')}: {w.get('display_name')}" + (f" [{venue}]" if venue else ""))
            if coauthors:
                lines.append(f"    co-authors: {', '.join(coauthors[:8])}")
            if w.get("doi"):
                lines.append(f"    doi: {w['doi']}")
        lines.append("")
    lines.append("Several same-name authors may appear; match on affiliation and years before attributing. Co-authors are connection leads.")
    return ToolResult(content="\n".join(lines), url=f"https://openalex.org/authors?search={name}", meta={"authors": len(authors), "works_listed": total_works})


openalex_lookup = Tool(
    name="openalex_lookup",
    description=("Scholarly footprint from OpenAlex (free index of papers): author records matching a name, their institutions with years, "
                 "recent works with venue, DOI and co-author names. Use it on any target with a research, academic or lab affiliation; "
                 "pass the institution as affiliation to rank the right namesake first. Co-authors are connection leads."),
    parameters={"type": "object", "properties": {
        "name": {"type": "string"}, "affiliation": {"type": "string", "description": "institution word to rank by, e.g. 'Berkeley'"},
        "max_authors": {"type": "integer", "default": 3}, "max_works": {"type": "integer", "default": 6}}, "required": ["name"]},
    fn=_openalex_lookup, requires=("openalex",),
)
