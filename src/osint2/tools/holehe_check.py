"""holehe_check: which services an email address is registered on, using the holehe library's
existence checks (registration and password-reset endpoints that answer "known" or "unknown" without
sending anything to the address). Free, keyless, but it does touch third-party sites with the
address, which is why it is a separate tool the operator enables deliberately. Returns registered
services, services that rate-limited the check, and the count that came back clean."""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from typing import Any

import httpx

from . import RunContext, Tool, ToolResult

TOTAL_TIMEOUT = 45.0
CONCURRENCY = 20
_MODULES: list[Any] = []


def _load_modules() -> list[Any]:
    if _MODULES:
        return _MODULES
    import holehe.modules
    for m in pkgutil.walk_packages(holehe.modules.__path__, "holehe.modules."):
        if m.ispkg:
            continue
        try:
            mod = importlib.import_module(m.name)
        except Exception:  # noqa: BLE001
            continue
        fn_name = m.name.rsplit(".", 1)[-1]
        fn = getattr(mod, fn_name, None)
        if callable(fn):
            _MODULES.append(fn)
    return _MODULES


async def _run_one(fn: Any, email: str, client: httpx.AsyncClient, sem: asyncio.Semaphore) -> dict[str, Any] | None:
    out: list[dict[str, Any]] = []
    try:
        async with sem:
            await asyncio.wait_for(fn(email, client, out), timeout=12)
    except Exception:  # noqa: BLE001
        return None
    return out[0] if out else None


async def _holehe_check(ctx: RunContext, email: str) -> ToolResult:
    email = email.strip().lower()
    if "@" not in email:
        return ToolResult(content="holehe_check needs an email address.", error="BadArguments", store_source=False)
    mods = _load_modules()
    if not mods:
        return ToolResult(content="holehe_check unavailable: holehe modules did not load.", error="Unavailable")
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        tasks = [asyncio.ensure_future(_run_one(fn, email, client, sem)) for fn in mods]
        done, pending = await asyncio.wait(tasks, timeout=TOTAL_TIMEOUT)
        for t in pending:
            t.cancel()
        results = [t.result() for t in done if not t.cancelled() and t.exception() is None and t.result()]
    registered = sorted({r["name"] for r in results if r.get("exists")})
    limited = sorted({r["name"] for r in results if r.get("rateLimit")})
    clean = sum(1 for r in results if not r.get("exists") and not r.get("rateLimit") and not r.get("error"))
    extras = {r["name"]: {k: v for k, v in r.items() if k in ("emailrecovery", "phoneNumber", "others") and v} for r in results if r.get("exists")}
    lines = [f"# holehe_check: {email}", f"services checked: {len(results)} of {len(mods)} ({len(pending)} timed out)",
             f"registered on ({len(registered)}): " + (", ".join(registered) or "none found")]
    for name, ex in extras.items():
        if ex:
            lines.append(f"  {name}: {ex}")
    if limited:
        lines.append(f"rate limited, unknown ({len(limited)}): " + ", ".join(limited[:20]))
    lines.append(f"not registered: {clean}")
    lines.append("\nA registration proves the address was used to sign up, not who the person is; record each service as an account finding with this source and mark personal services sensitive.")
    return ToolResult(content="\n".join(lines), url=f"https://github.com/megadose/holehe#{email}", meta={"registered": len(registered), "rate_limited": len(limited), "checked": len(results)})


holehe_check = Tool(
    name="holehe_check",
    description=("Which services an email address is registered on (holehe existence checks across ~140 sites, nothing is sent to the address). "
                 "Use on the target's confirmed emails to find accounts a username sweep cannot. Personal services (dating, gaming, adult) are sensitive."),
    parameters={"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]},
    fn=_holehe_check, requires=("holehe",),
)
