import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from trendforge.schemas import EntityInput, ObservationInput


class ProviderError(Exception):
    """A sanitized error safe to display; never include a request URL or secret."""


class RateLimited(ProviderError):
    pass


class NotConfigured(ProviderError):
    pass


@dataclass
class ProviderBatch:
    entities: list[EntityInput] = field(default_factory=list)
    observations: list[ObservationInput] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Transport:
    """Bounded retries, allowlisted HTTPS, timeout, throttling and in-run cache."""

    HOSTS = {"www.alphavantage.co", "api.github.com", "www.googleapis.com"}

    def __init__(self, client: httpx.AsyncClient | None = None, interval: float = 0.5) -> None:
        self.client = client
        self.interval = interval
        self.last_request = 0.0
        self.lock = asyncio.Lock()
        self.cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.stats: dict[str, Any] = {
            "requests": 0,
            "successes": 0,
            "cache_hits": 0,
            "retries": 0,
            "latency_ms": 0.0,
            "quota_remaining": None,
        }

    async def json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl: int = 300,
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.HOSTS
            or parsed.port not in (None, 443)
            or parsed.username
        ):
            raise ProviderError("Provider URL is not allowlisted")
        # Cache is memory-only and never persisted or logged (parameters may contain a key).
        key = repr((url, sorted((params or {}).items()), sorted((headers or {}).items())))
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < ttl:
            self.stats["cache_hits"] += 1
            return cached[1]
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=20, follow_redirects=False)
        try:
            for attempt in range(3):
                async with self.lock:
                    await asyncio.sleep(
                        max(0, self.interval - (time.monotonic() - self.last_request))
                    )
                    self.last_request = time.monotonic()
                    started = time.monotonic()
                    self.stats["requests"] += 1
                    try:
                        response = await client.get(url, params=params, headers=headers, timeout=20)
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        if attempt == 2:
                            raise ProviderError(
                                "Provider timed out or network is unavailable"
                            ) from exc
                        self.stats["retries"] += 1
                        await asyncio.sleep(2**attempt + random.uniform(0, 0.3))  # noqa: S311
                        continue
                    self.stats["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
                self.stats["quota_remaining"] = response.headers.get("x-ratelimit-remaining")
                limited = response.status_code == 429 or (
                    response.status_code == 403
                    and (
                        self.stats["quota_remaining"] == "0"
                        or "quota" in response.text[:1000].lower()
                    )
                )
                if limited:
                    raise RateLimited("Provider quota exhausted; retry on a later scheduled run")
                if response.status_code in (401, 403):
                    raise ProviderError("Provider denied credentials or permissions")
                if response.status_code >= 500:
                    if attempt < 2:
                        self.stats["retries"] += 1
                        await asyncio.sleep(2**attempt + random.uniform(0, 0.3))
                        continue
                    raise ProviderError("Provider server is unavailable after bounded retries")
                if response.is_error or response.is_redirect:
                    raise ProviderError(f"Provider returned HTTP {response.status_code}")
                if len(response.content) > 5_000_000:
                    raise ProviderError("Provider response exceeded the size limit")
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise ProviderError("Provider returned malformed JSON") from exc
                if not isinstance(payload, dict):
                    raise ProviderError("Provider returned an unexpected JSON shape")
                self.stats["successes"] += 1
                self.cache[key] = (time.monotonic(), payload)
                return payload
            raise ProviderError("Provider retries exhausted")
        finally:
            if owned:
                await client.aclose()


class TrendProvider(ABC):
    name: str
    capability: str = "OPTIONAL"
    expected_interval_hours: int = 24
    instructions: str = ""

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport or Transport()

    @property
    @abstractmethod
    def configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def fetch(self) -> ProviderBatch:
        raise NotImplementedError
