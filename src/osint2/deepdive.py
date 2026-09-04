"""Post-resolution deep dive (DEEP_DIVE=1). Once identity is RESOLVED, up to three read-only
subagents run in parallel, one per confirmed lead (the top handle, the personal domain, a recovered
email). Each is pinned to the resolved candidate: it cannot call record_candidate, and every claim
it records is stamped with the resolved candidate id. All three draw on the same Budget as the lead,
so rung 9 versus rung 8 is a test of parallel search at equal money, not of extra money."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from .config import BOOKKEEPING_TOOLS
from .llm import OpenRouterClient
from .resolution import Candidate
from .tools import RunContext, Tool, parse_tool_args, run_tool

MAX_SUBAGENTS = 4
SUB_MAX_STEPS = 6

SUB_PROMPT = """You are a read-only deep-dive investigator. Identity is already settled in code; you are handed ONE
confirmed lead about ONE confirmed person and you dig into that lead only. Do not try to identify anyone; do not
record candidates. Use the data tools on the lead, then record_claim every fact you read with its source_id and the
exact line quoted. Every claim you record is about the confirmed person; if a page is clearly about someone else with
the same name, do not record from it. Record not_found for what the lead did not yield. Call finish when the lead is
exhausted or nothing new turns up."""

SKIP_HOSTS = ("github.com", "linkedin.com", "x.com", "twitter.com", "gravatar.com", "facebook.com", "instagram.com")


def collect_leads(cand: Candidate, entities: Any = None) -> list[dict[str, str]]:
    leads: list[dict[str, str]] = []
    # Frontier first: connections and unread accounts derived from admitted claims.
    if entities is not None:
        for n in entities.frontier(12):
            if n.type == "person" and n.about == "connection" and not any(ld["kind"] == "connection" for ld in leads):
                via = n.hints.get("via") or n.hints.get("relation") or ""
                leads.append({"kind": "connection", "value": n.label, "task": (
                    f"Connection '{n.label}' ({via}). Identify this person's public profile: if it is a GitHub handle, github_intel(username) "
                    f"for the real name, then a web_search for that name (add the shared context: repo, school or employer) and exa_contents on the "
                    f"LinkedIn or personal page you find. Record what you learn as claims about THE TARGET with field 'connection_{n.label}' style "
                    f"fields (connection_name, connection_profile, connection_role, connection_tie) and the evidence tying them to the target. "
                    f"Someone with the same name is not the same person: require the shared context to appear in the page you cite.")})
            elif n.type == "account" and n.url and not any(ld["kind"] == "account" for ld in leads):
                leads.append({"kind": "account", "value": n.label, "task": f"Account {n.label} at {n.url}: read the page (exa_contents) and record what it states about this person: bio, activity, projects, dates."})
        leads = leads[:2]
    for h in cand.handles[:1]:
        leads.append({"kind": "handle", "value": h, "task": f"Handle '{h}': run whatsmyname on it and read the most informative profiles that clearly belong to this person."})
    for u in cand.profile_urls:
        host = urlparse(u if "://" in u else "https://" + u).netloc.lower().removeprefix("www.")
        if host and not any(host == s or host.endswith("." + s) for s in SKIP_HOSTS):
            leads.append({"kind": "domain", "value": host, "task": f"Personal domain {host}: read it (fetch_page or exa_contents if available) and its archived versions with wayback_lookup; recover old bios, projects, handles."})
            break
    for e in cand.emails[:1]:
        leads.append({"kind": "email", "value": e, "task": f"Email {e}: github_intel by email, gravatar_lookup, and a web_search for the address in quotes if search is available."})
    return leads[:MAX_SUBAGENTS]


def identity_context(cand: Candidate) -> str:
    return (f"Confirmed person: {cand.label}. Names {cand.names}; handles {cand.handles}; emails {cand.emails}; "
            f"profile URLs {cand.profile_urls}; employers {[e.name for e in cand.employers]}; education {[e.name for e in cand.education]}; "
            f"locations {cand.locations}.")


async def run_subagent(ctx: RunContext, llm: OpenRouterClient, tools: dict[str, Tool], cand: Candidate, lead: dict[str, str]) -> dict[str, Any]:
    thread = f"sub:{lead['kind']}"
    sub_tools = {k: v for k, v in tools.items() if k != "record_candidate"}
    specs = [t.spec() for t in sub_tools.values()]
    messages: list[dict[str, Any]] = [{"role": "system", "content": SUB_PROMPT},
                                      {"role": "user", "content": identity_context(cand) + "\n\nYour lead: " + lead["task"]}]
    admitted_before = len(ctx.store.claims)
    stop = "max_steps"
    for step in range(1, SUB_MAX_STEPS + 1):
        if ctx.budget.exhausted():
            stop = "budget"
            break
        result = await llm.chat(messages, specs, thread=thread, step=step)
        await ctx.budget.charge_llm(result.usage.get("cost_usd"))
        messages.append(result.message)
        if not result.tool_calls:
            stop = "no_tools"
            break
        done = False
        for tc in result.tool_calls:
            name = tc["function"]["name"]
            args = parse_tool_args(tc["function"].get("arguments"))
            if name == "finish":
                done = True
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": "done"})
                continue
            ctx.state["pin_candidate"] = cand.id
            res = await run_tool(sub_tools, name, args, ctx, step=step, thread=thread, tool_call_id=tc.get("id"))
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": res.content})
        if done:
            stop = "finish"
            break
    ctx.state.pop("pin_candidate", None)
    return {"lead": lead, "stop": stop, "admitted": len(ctx.store.claims) - admitted_before}


async def deep_dive(ctx: RunContext, llm: OpenRouterClient, tools: dict[str, Tool], cand: Candidate) -> list[dict[str, Any]]:
    leads = collect_leads(cand, ctx.state.get("entities"))
    ctx.trace.write("deep_dive", event="start", candidate=cand.id, leads=[ld["value"] for ld in leads], budget=ctx.budget.snapshot())
    if not leads:
        return []
    results = await asyncio.gather(*[run_subagent(ctx, llm, tools, cand, ld) for ld in leads], return_exceptions=True)
    out = []
    for ld, r in zip(leads, results):
        if isinstance(r, Exception):
            out.append({"lead": ld, "stop": "error", "error": f"{type(r).__name__}: {str(r)[:200]}", "admitted": 0})
        else:
            out.append(r)
    ctx.trace.write("deep_dive", event="end", results=out, budget=ctx.budget.snapshot())
    return out
