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
  - X: https://api.x.com/i/users/username_available.json?username=kvnalb
  - Fanslist: https://fanslist.com/search?q=kvnalb
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
    assert "account_docker_hub" in fields and "account_reddit" in fields and "account_x" not in fields and "account_fanslist" not in fields and "account_spotify" in fields and "account_eventbrite" in fields
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


FB = """# web_search (perplexity): "Kunal Baldava" UC Berkeley
results: 3

1. Kunal Baldava | Facebook
   url: https://www.facebook.com/kunal.baldava
   snippet: Kunal Baldava is on Facebook. Studies at UC Berkeley. Lives in Berkeley, California.

2. Kunal Baldava's post
   url: https://www.facebook.com/kunal.baldava/posts/123
   snippet: Kunal Baldava at UC Berkeley

3. Kunal Sharma | Facebook
   url: https://www.facebook.com/kunal.sharma.9
   snippet: Kunal Sharma is on Facebook. UC Berkeley alumni.
"""
IG = """# web_search (perplexity): "Kunal Baldava" UC Berkeley
results: 1

1. Kunal (@kvnalb)
   url: https://www.instagram.com/kvnalb/
   snippet: 120 followers. Kunal Baldava. photos from Goa
"""
FAM = """# web_search (exa): "Baldava" Mumbai
results: 3

1. Rohan Baldava - Analyst - Deloitte | LinkedIn
   url: https://in.linkedin.com/in/rohanbaldava
   snippet: Mumbai, Maharashtra
2. Kunal Baldava - UC Berkeley | LinkedIn
   url: https://www.linkedin.com/in/kunalbaldava
   snippet: Berkeley
3. Baldava Textiles Pvt Ltd | LinkedIn
   url: https://www.linkedin.com/company/baldava-textiles
   snippet: Mumbai
"""


def test_social_wave_gates_profiles_and_records_family_leads(tmp_path):
    calls = []

    def search(ctx, **kw):
        calls.append(kw)
        if kw.get("domains") == ["facebook.com"]:
            return ToolResult(content=FB, cost_usd=0.005)
        if kw.get("domains") == ["instagram.com"]:
            return ToolResult(content=IG, cost_usd=0.005)
        if kw.get("category") == "linkedin profile":
            return ToolResult(content=FAM, cost_usd=0.005)
        return ToolResult(content="# web_search (perplexity): x\nresults: 0\n\nNo results.", cost_usd=0.005)

    async def ws(ctx, **kw):
        return search(ctx, **kw)

    reads = []

    async def exa(ctx, **kw):
        reads.append(kw["url"])
        return ToolResult(content="Kunal Baldava. Studies at UC Berkeley. Brother: Rohan Baldava", url=kw["url"])

    tools = {"web_search": Tool(name="web_search", description="", parameters={"type": "object", "properties": {}}, fn=ws),
             "exa_contents": Tool(name="exa_contents", description="", parameters={"type": "object", "properties": {}}, fn=exa)}
    ctx, cand = make_ctx(tmp_path, tools)
    cand.handles = []; cand.emails = []; cand.locations = ["Mumbai, India"]
    import dataclasses
    ctx.settings = dataclasses.replace(ctx.settings, tools=tuple(ctx.settings.tools) + ("exa", "perplexity"))
    out = asyncio.run(sweep(ctx, tools, cand, step=3))
    queries = [c.get("query") for c in calls]
    assert any(c.get("domains") == ["facebook.com"] for c in calls) and any("high school" in q for q in queries)
    assert any(c.get("category") == "pdf" for c in calls) and any(c.get("category") == "linkedin profile" for c in calls)
    assert not any("obituary" in q for q in queries), "obituary search is US-only"
    found = {c.field: c for c in ctx.store.findings()}
    assert found["account_facebook"].value == "https://www.facebook.com/kunal.baldava"
    assert sum(1 for c in ctx.store.findings() if c.field == "account_facebook") == 1, "post URLs and namesakes are not profiles"
    assert "account_instagram" not in found, "instagram snippet without school or city does not pass the gate"
    lead = found["same_surname_in_city"]
    assert lead.value.startswith("Rohan Baldava - Analyst") and lead.sensitive
    assert sum(1 for c in ctx.store.findings() if c.field == "same_surname_in_city") == 1, "the person and the company are not leads"
    assert reads == ["https://www.facebook.com/kunal.baldava"] and out["social"] == 5
    assert ctx.budget.calls == 0 and abs(ctx.budget.usd - 0.025) < 1e-9, "paid sweep searches cost money but not calls"
    # a second sweep for the same name does not repeat the social wave
    before = len(calls)
    out2 = asyncio.run(sweep(ctx, tools, cand, step=4))
    assert out2["social"] == 0 and len(calls) == before


def test_entity_keys_must_tie_to_the_person(tmp_path):
    from osint2.sweep import _domains, _emails
    from osint2.entities import Node
    ctx, cand = make_ctx(tmp_path, {})
    ents = ctx.state["entities"]
    for nid, node in {
        "account:x:office365": Node(id="account:x:office365", type="account", label="x office365", about="target", hints={"handle": "office365"}),
        "account:x:kunal-baldava": Node(id="account:x:kunal-baldava", type="account", label="x kunal-baldava", about="target", hints={"handle": "kunal-baldava"}),
        "email:saqib.mumtaz.h@gmail.com": Node(id="email:saqib.mumtaz.h@gmail.com", type="email", label="saqib.mumtaz.h@gmail.com", about="target"),
        "email:kunalb@berkeley.edu": Node(id="email:kunalb@berkeley.edu", type="email", label="kunalb@berkeley.edu", about="target"),
        "domain:thegatewaypundit.com": Node(id="domain:thegatewaypundit.com", type="domain", label="thegatewaypundit.com", about="target"),
        "domain:kunalbaldava.com": Node(id="domain:kunalbaldava.com", type="domain", label="kunalbaldava.com", about="target"),
    }.items():
        ents.upsert(node)
    assert _handles(cand, ctx) == ["kvnalb", "kunal-baldava"]
    assert _emails(cand, ctx) == ["k@berkeley.edu", "kunalb@berkeley.edu"]
    assert _domains(cand, ctx) == ["kunalbaldava.com"]


def test_registration_label_is_not_a_handle_and_noisy_hosts_are_skipped(tmp_path):
    ctx, cand = make_ctx(tmp_path, {})
    sid = ctx.store.add_source("holehe_check", {"email": "k@berkeley.edu"}, "# holehe_check: k@berkeley.edu\nregistered on (1): office365\n", None, 1).id
    n, _ = _record(ctx, cand, "holehe_check", {"email": "k@berkeley.edu"}, ToolResult(content=ctx.store.source_text(sid), meta={"source_id": sid}), 1)
    assert n == 1
    ents = ctx.state["entities"]
    assert not any(nd.hints.get("handle") == "office365" for nd in ents.nodes.values())
    wmn = "# whatsmyname: kvnalb\n[news]\n  - The Gateway Pundit: https://www.thegatewaypundit.com/author/kvnalb/\n  - Twitch tracker: https://twitchtracker.com/kvnalb\n[coding]\n  - Kaggle: https://www.kaggle.com/kvnalb\n"
    sid2 = ctx.store.add_source("whatsmyname", {"username": "kvnalb"}, wmn, None, 1).id
    n2, _ = _record(ctx, cand, "whatsmyname", {"username": "kvnalb"}, ToolResult(content=wmn, meta={"source_id": sid2}), 1)
    assert n2 == 1 and not any(nd.type == "domain" for nd in ents.nodes.values())


def test_tool_commentary_is_rejected_as_a_value(tmp_path):
    ctx, cand = make_ctx(tmp_path, {})
    sid = ctx.store.add_source("exa_contents", {"url": "https://www.kaggle.com/x"}, "Both fetch_page and exa_contents returned only HTML framework without profile content", "https://www.kaggle.com/x", 1).id
    claim, reason = ctx.store.admit({"field": "kaggle_bio", "value": "Both fetch_page and exa_contents returned only HTML framework without profile content",
                                     "excerpt": "Both fetch_page and exa_contents returned only HTML framework", "source_id": sid}, step=1)
    assert claim is None and "tool result" in reason
