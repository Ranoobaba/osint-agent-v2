"""The sweep: once identity is RESOLVED, code (not the model) points every surface tool at the
confirmed keys, in parallel, without spending a model turn or a metered call. Handles get
whatsmyname, roblox_lookup and tinder_check; emails get holehe_check, gravatar_lookup and the GitHub
reverse search; personal domains get a Wayback listing and a read of the oldest capture; a resolved
US adult gets one people_search; whatsmyname hits on platforms with keyless JSON get profile_read.
Structured hits become claims through the same admission gate, quoting the tool's own line, with
sensitive set by surface, so the report and the ladder see them like any other finding. Readable hit
URLs become account nodes so the lead and the deep dive can read them.

Gates against false attribution: only handles that are identity markers or were recorded on a page
naming the resolved person; handles shorter than 5 characters or that are dictionary-like words are
skipped; tinder and people_search results are admitted only when the tool's own lines match the
candidate on name, school or city; roblox needs a description or previous username that ties back.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

from .resolution import Candidate
from .tools import RunContext, Tool, run_tool

MIN_HANDLE = 5
COMMON_WORDS = {"admin", "user", "test", "hello", "music", "gaming", "official", "sports", "photos", "world", "player", "berkeley", "student"}
READABLE = {"reddit.com": "reddit", "hub.docker.com": "dockerhub", "news.ycombinator.com": "hackernews", "keybase.io": "keybase", "chess.com": "chesscom", "lichess.org": "lichess"}
SENSITIVE_SVC = {"tinder", "bumble", "hinge", "grindr", "roblox", "steam", "twitch", "pornhub", "onlyfans", "patreon", "spotify", "duolingo", "strava", "discord", "xbox", "playstation"}
HIT_RE = re.compile(r"^\s*-\s*([^:]+):\s*(https?://\S+)\s*$", re.M)


def _handles(cand: Candidate, ctx: RunContext) -> list[str]:
    seen: list[str] = []
    linkedin = {urlparse(u if "://" in u else "https://" + u).path.rstrip("/").split("/")[-1].lower() for u in cand.profile_urls if "linkedin.com" in u}
    pool = list(cand.handles)
    ents = ctx.state.get("entities")
    if ents is not None:
        for n in ents.nodes.values():
            if n.type == "account" and n.hints.get("handle") and n.about in ("target", f"candidate:{cand.id}"):
                pool.append(n.hints["handle"])
    for h in pool:
        h = h.strip().lstrip("@")
        if len(h) < MIN_HANDLE or h.lower() in COMMON_WORDS or h.lower() in linkedin or re.fullmatch(r"[\d\-.]+", h):
            continue
        if h.lower() not in {x.lower() for x in seen}:
            seen.append(h)
    return seen[:3]


def _emails(cand: Candidate, ctx: RunContext) -> list[str]:
    pool = list(cand.emails)
    ents = ctx.state.get("entities")
    if ents is not None:
        pool += [n.label for n in ents.nodes.values() if n.type == "email" and n.about in ("target", f"candidate:{cand.id}")]
    out: list[str] = []
    for e in pool:
        e = e.strip().lower()
        if "@" in e and e not in out and not e.endswith("users.noreply.github.com"):
            out.append(e)
    return out[:3]


def _domains(cand: Candidate, ctx: RunContext) -> list[str]:
    ents = ctx.state.get("entities")
    if ents is None:
        return []
    return [n.label for n in ents.nodes.values() if n.type == "domain" and n.about in ("target", f"candidate:{cand.id}")][:2]


def _us_location(ctx: RunContext) -> str | None:
    for c in ctx.store.findings():
        f = (c.field or "").lower()
        if "location" in f or "city" in f:
            v = c.value
            if re.search(r"\b(United States|USA|U\.S\.|CA|NY|TX|WA|MA|IL|Bay Area|California|New York|Texas|Washington|Boston|Chicago|Seattle|Austin|Berkeley|Los Angeles|San Francisco)\b", v):
                return v
    return None


async def _call(ctx: RunContext, tools: dict[str, Tool], name: str, args: dict[str, Any], step: int):
    if name not in tools or name in ctx.state.get("disabled_tools", set()):
        return name, args, None
    res = await run_tool(tools, name, args, ctx, step=step, thread="sweep", metered=False)
    return name, args, res


def _admit(ctx: RunContext, sid: str, field: str, value: str, excerpt: str, category: str, sensitive: bool, cand_id: str, step: int) -> bool:
    claim, _ = ctx.store.admit({"field": field, "value": value, "excerpt": excerpt, "source_id": sid, "category": category,
                                "sensitive": sensitive, "candidate_id": cand_id}, step=step, thread="sweep", default_candidate=cand_id)
    if claim:
        ents = ctx.state.get("entities")
        if ents is not None:
            try:
                ents.ingest_claim(claim, cand_id)
            except Exception:  # noqa: BLE001
                pass
        ctx.trace.write("claim_admitted", step=step, claim_id=claim.id, kind="finding", field=field, value=value[:200], source_id=sid,
                        content_hash=claim.content_hash, method=claim.method, candidate_id=cand_id, excerpt=excerpt[:300], by="sweep")
    return bool(claim)


def _record(ctx: RunContext, cand: Candidate, name: str, args: dict[str, Any], res, step: int) -> tuple[int, list[dict[str, str]]]:
    """Turn a tool's structured lines into claims. Returns (admitted, readable hits for follow-up)."""
    sid = res.meta.get("source_id") if res and res.meta else None
    if not sid or res.error:
        return 0, []
    text = res.content
    n = 0
    hits: list[dict[str, str]] = []
    if name == "whatsmyname":
        for m in HIT_RE.finditer(text):
            site, url = m.group(1).strip(), m.group(2).strip()
            host = urlparse(url).netloc.lower().removeprefix("www.")
            svc = re.sub(r"[^a-z0-9]+", "_", site.lower()).strip("_")
            n += _admit(ctx, sid, f"account_{svc}", url, m.group(0).strip(), "online_presence", any(k in svc for k in SENSITIVE_SVC), cand.id, step)
            for h, plat in READABLE.items():
                if host == h or host.endswith("." + h):
                    hits.append({"platform": plat, "handle": args.get("username", ""), "url": url})
    elif name == "holehe_check":
        m = re.search(r"^registered on \((\d+)\): (.+)$", text, re.M)
        if m and m.group(2).strip() != "none found":
            for svc in [x.strip() for x in m.group(2).split(",") if x.strip()]:
                n += _admit(ctx, sid, f"account_{re.sub(r'[^a-z0-9]+', '_', svc.lower())}", svc, m.group(0).strip(), "online_presence", svc.lower() in SENSITIVE_SVC, cand.id, step)
    elif name == "roblox_lookup" and "user id:" in text:
        # only when something ties the account back: a description, or a previous username equal to a known handle/name
        prev = re.search(r"^previous usernames: (.+)$", text, re.M)
        desc = re.search(r"^description: (.+)$", text, re.M)
        known = {h.lower() for h in cand.handles} | {x.lower() for x in cand.names}
        tie = (desc is not None and any(k in desc.group(1).lower() for k in known)) or (prev is not None and any(p.strip().lower() in known for p in prev.group(1).split(",")))
        if tie:
            for line_re, field in ((r"^(display name: .+)$", "roblox_account"), (r"^(previous usernames: .+)$", "roblox_previous_usernames")):
                mm = re.search(line_re, text, re.M)
                if mm:
                    n += _admit(ctx, sid, field, mm.group(1).split(":", 1)[1].strip()[:120], mm.group(1), "personal", True, cand.id, step)
    elif name == "tinder_check" and "public web profile:" in text:
        nm = re.search(r"^name: (\S+)", text, re.M)
        schools = re.search(r"^schools: (.+)$", text, re.M)
        first = (cand.names[0].split()[0].lower() if cand.names else "")
        school_ok = schools is not None and any(e.name.lower()[:8] in schools.group(1).lower() for e in cand.education)
        if nm and first and nm.group(1).lower() == first and school_ok:
            for line_re, field in ((r"^(name: .+)$", "tinder_profile"), (r"^(schools: .+)$", "tinder_schools"), (r"^(jobs: .+)$", "tinder_jobs")):
                mm = re.search(line_re, text, re.M)
                if mm:
                    n += _admit(ctx, sid, field, mm.group(1).split(":", 1)[1].strip()[:120], mm.group(1), "personal", True, cand.id, step)
    elif name == "gravatar_lookup" and "profile (" in text:
        mm = re.search(r"^(profile \(.+)$", text, re.M)
        if mm:
            n += _admit(ctx, sid, "gravatar_profile", mm.group(1)[:160], mm.group(1), "online_presence", False, cand.id, step)
    return n, hits


async def sweep(ctx: RunContext, tools: dict[str, Tool], cand: Candidate, step: int) -> dict[str, Any]:
    handles, emails, domains = _handles(cand, ctx), _emails(cand, ctx), _domains(cand, ctx)
    loc = _us_location(ctx)
    jobs: list[tuple[str, dict[str, Any]]] = []
    for h in handles:
        jobs += [("whatsmyname", {"username": h}), ("roblox_lookup", {"username": h}), ("tinder_check", {"username": h})]
    for e in emails:
        jobs += [("holehe_check", {"email": e}), ("gravatar_lookup", {"email": e}), ("github_intel", {"email": e})]
    for d in domains:
        jobs += [("wayback_lookup", {"url": d, "mode": "list", "limit": 20}), ("wayback_lookup", {"url": d, "mode": "read", "max_chars": 6000})]
    if loc and cand.names:
        jobs.append(("people_search", {"name": cand.names[0], "city_or_state": loc}))
    ctx.trace.write("sweep", event="start", step=step, handles=handles, emails=emails, domains=domains, location=loc, jobs=len(jobs))
    results = await asyncio.gather(*[_call(ctx, tools, n, a, step) for n, a in jobs])
    admitted = 0
    follow: list[dict[str, str]] = []
    for name, args, res in results:
        if res is None:
            continue
        n, hits = _record(ctx, cand, name, args, res, step)
        admitted += n
        follow += hits
    # second wave: keyless profile reads for the platforms the sweep flagged
    seen = set()
    wave2 = []
    for h in follow:
        k = (h["platform"], h["handle"].lower())
        if k not in seen and "profile_read" in tools:
            seen.add(k); wave2.append(("profile_read", {"platform": h["platform"], "handle": h["handle"]}))
    if wave2:
        await asyncio.gather(*[_call(ctx, tools, n, a, step) for n, a in wave2[:6]])
    ctx.state["swept"] = True
    ctx.state["step_admitted"] = ctx.state.get("step_admitted", 0) + admitted
    out = {"handles": handles, "emails": emails, "domains": domains, "people_search": bool(loc), "calls": len(jobs) + len(wave2), "admitted": admitted,
           "profile_reads": [f"{a['platform']}:{a['handle']}" for _, a in wave2[:6]]}
    ctx.trace.write("sweep", event="end", step=step, **out)
    return out
