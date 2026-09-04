"""The lead loop. The model chooses pivots and proposes candidates and claims through tools; code
owns identity, admission, budget, stopping, and the report. The prompt is short on purpose: every
nudge beyond it is an env flag so the ladder can measure it."""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .anchors import parse_anchor
from .budget import Budget
from .config import Settings
from .deepdive import deep_dive
from .entities import EntityGraph
from .evidence import EvidenceStore
from .llm import OpenRouterClient
from .report import build_report
from .resolution import Resolution, apply_judge, judge_candidates
from .tools import RunContext, parse_tool_args, registry, run_tool
from .trace import TraceWriter, read_trace, summarize_trace
from .workspace import Workspace, new_run_id

SYSTEM_PROMPT = """You are a people-intelligence investigator. One line of text names a target person. Your job is to
find who they are and what is publicly knowable about them, and to record it through tools. You never write
the final report; it is assembled from what you record.

How to work:
1. Identity first. Every plausible person you meet goes through record_candidate, including ones you think are
   wrong. Code scores them. Findings you record before the status is RESOLVED must carry a candidate_id.
   Someone with the same name is not the same person: a name plus a school or a city is never enough; a hard
   key (email, handle, profile URL, avatar) or two independent domains agreeing on employer and location is.
   If two candidates both fit and nothing separates them, leave it ambiguous; do not pick.
2. Record as you go. When a tool result states a fact, call record_claim right then with the source_id the
   tool returned and the exact sentence quoted verbatim. Facts you do not record are lost. Facts you cannot
   support with a quote from a source in this run do not exist; do not record from memory.
3. Wrong is worse than missing. If you looked for something and could not establish it, record_not_found.
   If two sources disagree, record a conflict. Inference goes in a synthesis claim resting on admitted findings.
4. Pivot on what you find: an email leads to Gravatar and account lookups; a handle leads to platforms; a
   personal domain leads to archives; an employer leads to colleagues and talks; a collaborator, co-author
   or teammate is a person to identify (their public profile, and the evidence tying them to the target).
   An account you found but have not read is not a finding yet; read it. A research affiliation means
   openalex_lookup. Old resumes and CVs (search "<name>" filetype:pdf) hold facts nothing else does.
   Once a handle is confirmed, sweep it (whatsmyname) and check the platforms that keep public account
   pages (roblox_lookup, tinder_check when available); once an email is confirmed, holehe_check tells you
   which services it is registered on. Gaming, dating and other personal-life accounts are recorded with
   sensitive=true, and only after the page itself ties the account to this person.
5. Stop when nothing new turns up. Call finish with one sentence. Budget is limited; spend calls on new
   leads, not on re-reading pages you already have.

Every tool result that carries a [source_id: sNNN] line is quotable. Bookkeeping tools (record_candidate,
record_claim, record_not_found, finish) are free; data tools count against the budget."""


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def recitation(ctx: RunContext, step: int, store: EvidenceStore) -> str:
    """Code-built state summary, capped near 1,500 chars. The window is pruned, so this is what the
    model remembers between steps."""
    anchor = ctx.state["anchor"]
    res: Optional[Resolution] = ctx.state.get("resolution")
    cands = ctx.state.get("candidates", [])
    b = ctx.budget.remaining()
    lead_left = max(0, ctx.state.get("lead_call_cap", ctx.budget.max_calls) - ctx.budget.calls)
    lines = [f"STEP {step}. Budget left: {lead_left} data calls for you" + (f" (then {b['calls'] - lead_left} reserved for deep-dive subagents)" if b['calls'] > lead_left else "") + f", ${b['usd']:.2f}, {int(b['seconds'])}s.",
             f"Target: {anchor.raw!r} (type {anchor.target_type}; names {anchor.names}; emails {anchor.emails}; "
             f"handles {anchor.handles}; companies {[c.name for c in anchor.companies]}; roles {anchor.roles}; locations {anchor.locations})"]
    if res is None:
        lines.append("Identity: no candidates recorded yet. Find the person; record every plausible profile.")
    else:
        lines.append(f"Identity: {res.status.upper()} best={res.best_candidate_id} score={res.score:.2f} markers={res.matched_markers}")
        for c in cands[:6]:
            bd = next((x for x in res.breakdowns if x.candidate_id == c.id), None)
            lines.append(f"  {c.id}: {c.label[:60]} score={bd.score if bd else 0:.2f}" + (" VETO" if bd and bd.contradictions else ""))
    fields: dict[str, int] = {}
    for c in store.findings():
        fields[c.field] = fields.get(c.field, 0) + 1
    lines.append(f"Recorded: {len(store.findings())} findings ({', '.join(f'{k}x{v}' for k, v in list(fields.items())[:14])}), "
                 f"{sum(1 for c in store.claims if c.kind == 'not_found')} not_found, {len(store.rejected)} rejected.")
    read = [s.url for s in store.sources.values() if s.url][-8:]
    if read:
        lines.append("Already read (do not re-fetch): " + "; ".join(read))
    if "NUDGE_FRONTIER" in ctx.settings.nudges:
        ft = ctx.state["entities"].frontier_text(6)
        if ft:
            lines.append(ft)
    if "NUDGE_INPUT_SHAPE" in ctx.settings.nudges:
        first = {"email": "First move: github_intel by email and gravatar_lookup on the address.",
                 "handle": "First move: github_intel by username and a whatsmyname sweep.",
                 "role_at_company": "First move: identify who holds the role before researching anyone.",
                 "name": "Expect namesakes. Gather a disambiguator (employer, handle) before trusting any profile."}
        lines.append(first.get(anchor.target_type, ""))
    text = "\n".join(lines)
    return text[:2400]


def _prune(messages: list[dict[str, Any]], keep_steps: int, step: int) -> None:
    """Replace tool results older than keep_steps with a stub. Files stay on disk."""
    for m in messages:
        if m.get("role") == "tool" and m.get("_step", step) < step - keep_steps and not m.get("_pruned"):
            sid = m.get("_source_id")
            m["content"] = f"[result pruned from context; {'source ' + sid + ' is still quotable' if sid else 'see trace'}]"
            m["_pruned"] = True


async def run_investigation(target: str, settings: Settings, runs_dir: Path | None = None,
                            on_step: Optional[Callable[[dict[str, Any]], None]] = None,
                            run_id: str | None = None) -> tuple[dict[str, Any], Workspace]:
    runs_dir = runs_dir or settings.runs_dir
    ws = Workspace(runs_dir, run_id or new_run_id())
    trace = TraceWriter(ws.trace_path, ws.run_id)
    store = EvidenceStore(ws)
    budget = Budget(settings.max_tool_calls, settings.max_usd, settings.max_seconds)
    llm = OpenRouterClient(settings, trace)
    ctx = RunContext(ws=ws, trace=trace, store=store, budget=budget, settings=settings)
    entities = EntityGraph(ws)
    entities.ingest_target(target)
    ctx.state["entities"] = entities
    tools = registry(settings)
    specs = [t.spec() for t in tools.values()]
    started = time.perf_counter()
    trace.write("invoke_agent", event="start", target=target, flags=settings.flags(), tools=list(tools))
    ws.write_json("input.json", {"target": target, "flags": settings.flags()})

    anchor = await parse_anchor(target, llm, settings)
    ctx.state["anchor"] = anchor
    ws.write_json("anchor.json", anchor.model_dump())
    trace.write("anchor", anchor=anchor.model_dump())

    # When the deep dive is on, the lead hands off with a share of the call budget still unspent, so the
    # subagents can actually run. The share is one quarter of the calls, at least 4 and at most 8.
    lead_call_cap = settings.max_tool_calls - (min(8, max(4, settings.max_tool_calls // 4)) if settings.deep_dive else 0)
    ctx.state["lead_call_cap"] = lead_call_cap
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    stop_reason = "max_steps"
    dry = 0
    step = 0
    error = None
    try:
        for step in range(1, settings.max_steps + 1):
            ctx.state["step"] = step
            ctx.state["step_admitted"] = 0
            ctx.state["step_candidates"] = 0
            sources_before = len(store.sources)
            ex = budget.exhausted()
            if ex:
                stop_reason = f"budget:{ex}"
                break
            if budget.calls >= lead_call_cap:
                stop_reason = "handoff"
                break
            if settings.prune_steps > 0:
                _prune(messages, keep_steps=settings.prune_steps, step=step)
            messages.append({"role": "user", "content": recitation(ctx, step, store)})
            send = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
            result = await llm.chat(send, specs, step=step)
            await budget.charge_llm(result.usage.get("cost_usd"))
            messages.append(result.message)
            if not result.tool_calls:
                # a bare text reply is a wasted step; nudge once toward tools, then treat as finish
                dry += 1
                if dry >= settings.saturation_dry_steps:
                    stop_reason = "saturation"
                    break
                messages.append({"role": "user", "content": "Use the tools: record what you know, search for more, or call finish."})
                continue
            for tc in result.tool_calls:
                name = tc["function"]["name"]
                args = parse_tool_args(tc["function"].get("arguments"))
                res = await run_tool(tools, name, args, ctx, step=step, tool_call_id=tc.get("id"))
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": res.content,
                                 "_step": step, "_source_id": res.meta.get("source_id")})
            if on_step:
                r = ctx.state.get("resolution")
                on_step({"step": step, "status": r.status if r else "unresolved", "score": r.score if r else 0.0,
                         "tool_calls": budget.calls, "admitted": len(store.claims), "usd": round(budget.usd, 3),
                         "last_tool": result.tool_calls[-1]["function"]["name"]})
            if ctx.state.get("finish"):
                stop_reason = "finish"
                break
            if ctx.state["step_admitted"] == 0 and ctx.state["step_candidates"] == 0 and len(store.sources) == sources_before:
                dry += 1
            else:
                dry = 0
            if dry >= settings.saturation_dry_steps:
                stop_reason = "saturation"
                break
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {str(exc)[:300]}"
        stop_reason = "error"
        trace.write("error", step=step, error=error)

    res: Resolution = ctx.state.get("resolution") or Resolution()
    cands = ctx.state.get("candidates", [])
    same_person: set[str] = set()
    deep_results: list[dict[str, Any]] = []
    if settings.deep_dive and res.status == "resolved" and not budget.exhausted() and error is None:
        best = next((c for c in cands if c.id == res.best_candidate_id), None)
        if best is not None:
            try:
                deep_results = await deep_dive(ctx, llm, tools, best)
            except Exception as exc:  # noqa: BLE001
                trace.write("deep_dive", event="error", error=f"{type(exc).__name__}: {str(exc)[:200]}")
    # The judge runs only in the ambiguous band and never overrides a veto (apply_judge enforces both).
    if res.status == "ambiguous" and cands and settings.judge_model:
        try:
            ranked = sorted(res.breakdowns, key=lambda b: -b.score)[:3]
            top_ids = {b.candidate_id for b in ranked}
            top = [c for c in cands if c.id in top_ids]
            evidence_lines = [f"[{c.id}] {e.claim} ({e.source_url})" for c in top for e in c.evidence]
            evidence_lines += [f"[{cl.candidate_id}] {cl.field}={cl.value} ({cl.source_url}) excerpt: {(cl.excerpt or '')[:200]}"
                               for cl in store.findings() if cl.candidate_id in top_ids]
            judge = await judge_candidates(llm, settings.judge_model, anchor, top, ranked, "\n".join(evidence_lines))
            await budget.charge_llm(0.0)
            res = apply_judge(res, judge)
            ws.write_json("resolution.json", res.model_dump())
            trace.write("judge", verdict=judge.verdict, candidate_id=judge.candidate_id, reasons=judge.reasons,
                        same_person_ids=judge.same_person_ids, status_after=res.status, model=judge.model)
            if judge.verdict == "same":
                same_person |= set(judge.same_person_ids)
        except Exception as exc:  # noqa: BLE001
            trace.write("judge", error=f"{type(exc).__name__}: {str(exc)[:200]}")
    # strip private keys before the trace summary; messages are not persisted
    duration = round(time.perf_counter() - started, 1)
    stats = summarize_trace(read_trace(ws.trace_path))
    run = {**stats, "duration_s": duration, "stop_reason": stop_reason, "steps": step, "error": error,
           "budget": budget.snapshot(), "flags": settings.flags(), "model": settings.lead_model,
           "git_sha": _git_sha(), "run_id": ws.run_id, "trace_path": str(ws.trace_path),
           "unsupported_candidates": ctx.state.get("unsupported_candidates", 0), "deep_dive": deep_results, **store.stats()}
    entities.persist()
    run["entities"] = entities.summary()
    report = build_report(anchor, res, cands, store, run, same_person)
    report["entities"] = entities.to_report()
    ws.write_json("report.json", report)
    ws.write_json("graph.json", report["graph"])
    trace.write("report_emitted", findings=len(report["findings"]), excluded=len(report["excluded_findings"]),
                not_found=len(report["not_found"]), identity=report["identity"]["status"])
    trace.write("invoke_agent", event="end", stop_reason=stop_reason, duration_s=duration, cost_usd=stats.get("cost_usd"),
                budget=budget.snapshot())
    return report, ws


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -m osint2.agent '<target>'")
    settings = Settings.from_env()
    report, ws = asyncio.run(run_investigation(sys.argv[1], settings))
    print(json.dumps({"run_id": ws.run_id, "identity": report["identity"]["status"], "name": report["identity"]["name"],
                      "findings": len(report["findings"]), "excluded": len(report["excluded_findings"]),
                      "not_found": len(report["not_found"]), "run": {k: report["run"][k] for k in ("stop_reason", "duration_s", "cost_usd", "tool_calls", "proposed", "admitted", "rejected")}}, indent=2))


if __name__ == "__main__":
    main()
