"""Shared httpx helper with one retry on transient failures."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

TRANSIENT = {429, 500, 502, 503, 504}
UA = "osint-agent-v2"


async def request_with_retry(method: str, url: str, *, retries: int = 2, timeout: float = 40.0, **kwargs: Any) -> tuple[httpx.Response, int]:
    attempt = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        while True:
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code in TRANSIENT and attempt < retries:
                    attempt += 1
                    await asyncio.sleep(1.5 * attempt)
                    continue
                return response, attempt
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError):
                if attempt >= retries:
                    raise
                attempt += 1
                await asyncio.sleep(1.5 * attempt)
