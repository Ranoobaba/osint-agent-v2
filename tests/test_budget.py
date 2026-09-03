import asyncio

from osint2.budget import Budget


def test_calls_bind_first():
    b = Budget(max_calls=2, max_usd=10, max_seconds=100)

    async def go():
        t1 = await b.reserve("github_intel")
        t2 = await b.reserve("github_intel")
        t3 = await b.reserve("github_intel")
        return t1, t2, t3
    t1, t2, t3 = asyncio.run(go())
    assert t1 and t2 and t3 is None
    assert b.exhausted() == "calls"


def test_usd_binds_with_tool_estimate_and_settle():
    b = Budget(max_calls=100, max_usd=0.01, max_seconds=100)

    async def go():
        t = await b.reserve("web_search")   # 0.005 estimate
        await b.settle(t, 0.004)
        t2 = await b.reserve("web_search")  # 0.004 + 0.005 = 0.009 ok
        t3 = await b.reserve("web_search")  # 0.014 > 0.01
        return t, t2, t3
    t, t2, t3 = asyncio.run(go())
    assert t and t2 and t3 is None
    assert abs(b.tool_usd - 0.009) < 1e-9


def test_llm_charge_counts_toward_usd():
    b = Budget(max_calls=100, max_usd=1.0, max_seconds=100)
    asyncio.run(b.charge_llm(0.6))
    asyncio.run(b.charge_llm(0.5))
    assert b.exhausted() == "usd"
    assert b.snapshot()["llm_usd"] == 1.1


def test_concurrent_reserves_never_exceed_cap():
    b = Budget(max_calls=5, max_usd=10, max_seconds=100)

    async def go():
        tickets = await asyncio.gather(*[b.reserve("github_intel") for _ in range(20)])
        return [t for t in tickets if t]
    got = asyncio.run(go())
    assert len(got) == 5 and b.calls == 5
