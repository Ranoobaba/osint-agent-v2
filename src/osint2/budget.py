"""One budget per run, shared by the lead and every subagent. Three caps, the tightest binds.
Data-tool calls are reserved before they run (atomic under a lock) and settled after with the
actual cost. LLM cost is charged after each call. Bookkeeping tools never touch the call counter."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from .config import TOOL_PRICES


@dataclass
class Ticket:
    tool: str
    estimate: float
    n: int


@dataclass
class Budget:
    max_calls: int
    max_usd: float
    max_seconds: float
    calls: int = 0
    usd: float = 0.0
    llm_usd: float = 0.0
    tool_usd: float = 0.0
    started: float = field(default_factory=time.monotonic)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def exhausted(self) -> Optional[str]:
        if self.calls >= self.max_calls:
            return "calls"
        if self.usd >= self.max_usd:
            return "usd"
        if self.elapsed() >= self.max_seconds:
            return "seconds"
        return None

    def remaining(self) -> dict[str, float]:
        return {"calls": max(0, self.max_calls - self.calls), "usd": round(max(0.0, self.max_usd - self.usd), 4),
                "seconds": round(max(0.0, self.max_seconds - self.elapsed()))}

    async def reserve(self, tool: str) -> Optional[Ticket]:
        """Reserve one data-tool call. None means the run is out of budget; the caller stops."""
        async with self._lock:
            estimate = TOOL_PRICES.get(tool, 0.0)
            if self.calls >= self.max_calls or self.usd + estimate > self.max_usd or self.elapsed() >= self.max_seconds:
                return None
            self.calls += 1
            self.usd += estimate
            self.tool_usd += estimate
            return Ticket(tool=tool, estimate=estimate, n=self.calls)

    async def settle(self, ticket: Ticket, actual_usd: float) -> None:
        async with self._lock:
            delta = actual_usd - ticket.estimate
            self.usd += delta
            self.tool_usd += delta

    async def charge_llm(self, usd: float | None) -> None:
        if not usd:
            return
        async with self._lock:
            self.usd += usd
            self.llm_usd += usd

    async def charge_tool(self, usd: float | None) -> None:
        """A paid call made outside the call cap (the code-driven sweep) still costs money."""
        if not usd:
            return
        async with self._lock:
            self.usd += usd
            self.tool_usd += usd

    def snapshot(self) -> dict[str, float]:
        return {"calls": self.calls, "max_calls": self.max_calls, "usd": round(self.usd, 4), "max_usd": self.max_usd,
                "llm_usd": round(self.llm_usd, 4), "tool_usd": round(self.tool_usd, 4),
                "elapsed_s": round(self.elapsed(), 1), "max_seconds": self.max_seconds}
