# services/http.py
from __future__ import annotations

import aiohttp
from typing import Optional

from config import settings


class HttpClient:
    """
    Owns one aiohttp session for the whole bot lifecycle.
    """
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=25)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=settings.headers,
            )
        return self._session

    async def fetch_html(self, url: str) -> str:
        session = await self.get_session()
        async with session.get(url) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} for {url}\n{text[:300]}")
            return text

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# Shared instance to import everywhere
http = HttpClient()
