import asyncio
import json

from osint2.budget import Budget
from osint2.evidence import EvidenceStore
from osint2.resolution import Candidate, Employment, Evidence, Resolution
from osint2.sweep import _handles, _record, sweep
from osint2.tools import RunContext, Tool, ToolResult
from osint2.trace import TraceWriter
from osint2.workspace import Workspace
from osint2.config import Settings
from osint2.entities import EntityGraph

WMN = """# whatsmyname: kvnalb
checked 700 curated sites, found on 3

[coding]
  - Docker Hub: https://hub.docker.com/u/kvnalb
[social]
  - Reddit: https://www.reddit.com/user/kvnalb
  - Roblox: https://www.roblox.com/user.aspx?username=kvnalb
"""
HOLEHE = """# holehe_check: k@berkeley.edu
services checked: 100 of 140 (3 timed out)
registered on (3): eventbrite, spotify, twitter
not registered: 90
"""


def make_ctx(tmp_path, tools):
    ws = Workspace(tmp_path, "r")
    settings = Settings.from_env({"TOOLS": "github,gravatar,wayback,whatsmyname,roblox,tinder,holehe,profiles", "OPENROUTER_API_KEY": "x"})
    ctx = RunContext(ws=ws, trace=TraceWriter(ws.trace_path, "r"), store=EvidenceStore(ws), budget=Budget(20, 5, 100), settings=settings)
    ctx.state["entities"] = EntityGraph(ws)
    ctx.state["entities"].ingest_target("kunal")
    cand = Candidate(id="cand1", label="Kunal Baldava, GitHub kvnalb", names=["Kunal Baldava"], handles=["kvnalb", "ab"], emails=["k@berkeley.edu"],
                     profile_urls=["https://www.linkedin.com/in/kunalbaldava"], education=[Employment(name="UC Berkeley")],
                     evidence=[Evidence(claim="x", source_url="https://github.com/kvnalb")])
    ctx.state["candidates"] = [cand]
    ctx.state["resolution"] = Resolution(status="resolved", best_candidate_id="cand1", score=1.0)
    return ctx, cand


def fake_tool(name, content, url=None):
    async def fn(ctx, **kw):
        return ToolResult(content=content, url=url)
    return Tool(name=name, description="", parameters={"type": "object", "properties": {}}, fn=fn)


def test_handles_skip_short_and_linkedin_slugs(tmp_path):
    ctx, cand = make_ctx(tmp_path, {})
    cand.handles.append("kunalbaldava")
    assert _handles(cand, ctx) == ["kvnalb"]


def test_sweep_records_hits_and_registrations_and_reads_profiles(tmp_path):
    calls = []

    def counting(name, content, url=None):
        async def fn(ctx, **kw):
            calls.append((name, kw))
            return ToolResult(content=content, url=url)
        return Tool(name=name, description="", parameters={"type": "object", "properties": {}}, fn=fn)

    tools = {
        "whatsmyname": counting("whatsmyname", WMN, "https://whatsmyname.app/?q=kvnalb"),
        "roblox_lookup": counting("roblox_lookup", "# roblox_lookup: kvnalb\nNo Roblox account with this exact username."),
        "tinder_check": counting("tinder_check", "# tinder_check: kvnalb\nNo public Tinder web profile for this username."),
        "holehe_check": counting("holehe_check", HOLEHE),
        "gravatar_lookup": counting("gravatar_lookup", "# gravatar_lookup: k@berkeley.edu\nsha256: abc\navatar: none\n\nNo public Gravatar profile."),
        "github_intel": counting("github_intel", "# github_intel: email k@berkeley.edu\naccounts with this public email: none"),
        "profile_read": counting("profile_read", "# profile_read: reddit kvnalb\nprofile: https://www.reddit.com/user/kvnalb  created: 2020-01-01"),
    }
    ctx, cand = make_ctx(tmp_path, tools)
    out = asyncio.run(sweep(ctx, tools, cand, step=3))
    names = [c[0] for c in calls]
    assert names.count("whatsmyname") == 1 and "holehe_check" in names and "roblox_lookup" in names and "tinder_check" in names
    assert ctx.budget.calls == 0, "sweep calls are not metered against the call cap"
    fields = {c.field for c in ctx.store.findings()}
    assert "account_docker_hub" in fields and "account_reddit" in fields and "account_spotify" in fields and "account_eventbrite" in fields
    spotify = next(c for c in ctx.store.findings() if c.field == "account_spotify")
    assert spotify.sensitive and spotify.excerpt.startswith("registered on")
    assert out["admitted"] >= 6 and any(p.startswith("reddit:") for p in out["profile_reads"]) and any(p.startswith("dockerhub:") for p in out["profile_reads"])
    assert ctx.state["swept"] is True


def test_roblox_and_tinder_need_a_tie(tmp_path):
    ctx, cand = make_ctx(tmp_path, {})
    sid = ctx.store.add_source("roblox_lookup", {"username": "kvnalb"}, "# roblox_lookup: kvnalb\nuser id: 5\ndisplay name: someone  created: 2015-01-01\nprevious usernames: none on record\nfriends: 3", "https://www.roblox.com/users/5/profile", 1).id
    res = ToolResult(content=ctx.store.source_text(sid), meta={"source_id": sid})
    n, _ = _record(ctx, cand, "roblox_lookup", {"username": "kvnalb"}, res, 1)
    assert n == 0
    sid2 = ctx.store.add_source("roblox_lookup", {"username": "kvnalb"}, "# roblox_lookup: kvnalb\nuser id: 6\ndisplay name: Kunal  created: 2015-01-01\nprevious usernames: kvnalb, oldname\nfriends: 3", "https://www.roblox.com/users/6/profile", 1).id
    res2 = ToolResult(content=ctx.store.source_text(sid2), meta={"source_id": sid2})
    n2, _ = _record(ctx, cand, "roblox_lookup", {"username": "kvnalb"}, res2, 1)
    assert n2 == 2 and all(c.sensitive for c in ctx.store.findings())
