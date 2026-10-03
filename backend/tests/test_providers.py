from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from trendforge.db import ProviderState
from trendforge.pipeline import update
from trendforge.providers.base import (
    ProviderError,
    RateLimited,
    Transport,
    TrendProvider,
)
from trendforge.providers.demo import DemoProvider
from trendforge.providers.finance import AlphaVantageProvider
from trendforge.providers.github import GitHubProvider
from trendforge.providers.youtube import YouTubeProvider


def transport(handler):
    return Transport(httpx.AsyncClient(transport=httpx.MockTransport(handler)), interval=0)


async def test_finance_normalizes_complete_daily_bars():
    payload = {
        "Meta Data": {"5. Time Zone": "US/Eastern"},
        "Time Series (Daily)": {
            "2026-01-05": {
                "1. open": "100",
                "2. high": "104",
                "3. low": "99",
                "4. close": "103",
                "5. volume": "100000",
            }
        },
    }
    provider = AlphaVantageProvider(
        "test-only", ["IBM"], transport(lambda r: httpx.Response(200, json=payload))
    )
    batch = await provider.fetch()
    assert len(batch.observations) == 5
    assert batch.entities[0].id == "av:IBM"
    close = next(r for r in batch.observations if r.metric == "close")
    assert close.value == 103
    assert close.source_timestamp.hour == 4  # January US/Eastern 23:59 -> next UTC day 04:59
    assert close.metadata["adjustment"] == "raw_unadjusted"
    assert not close.synthetic


async def test_finance_invalid_rows_are_not_ingested():
    provider = AlphaVantageProvider(
        "test-only",
        ["IBM"],
        transport(
            lambda r: httpx.Response(
                200, json={"Time Series (Daily)": {"2026-01-05": {"1. open": "100"}}}
            )
        ),
    )
    batch = await provider.fetch()
    assert not batch.observations
    assert batch.warnings


@pytest.mark.parametrize(
    "payload,exception",
    [
        ({"Note": "quota"}, RateLimited),
        ({"Error Message": "bad key"}, ProviderError),
        ({}, ProviderError),
    ],
)
async def test_finance_key_quota_and_empty_errors(payload, exception):
    provider = AlphaVantageProvider(
        "test-only", ["IBM"], transport(lambda r: httpx.Response(200, json=payload))
    )
    with pytest.raises(exception):
        await provider.fetch()


async def test_github_snapshots_do_not_invent_history():
    provider = GitHubProvider(
        ["owner/repo"],
        transport=transport(
            lambda r: httpx.Response(
                200,
                json={
                    "stargazers_count": 120,
                    "forks_count": 12,
                    "open_issues_count": 3,
                    "created_at": "2025-01-01T00:00:00Z",
                    "topics": ["ai"],
                },
            )
        ),
    )
    batch = await provider.fetch()
    assert len(batch.observations) == 3
    assert len({r.source_timestamp for r in batch.observations}) == 1
    assert batch.observations[0].metadata["snapshot_only"]
    assert batch.entities[0].primary_metric == "stars"


async def test_github_private_profiles_are_excluded():
    provider = GitHubProvider(
        ["owner/repo"],
        transport=transport(
            lambda r: httpx.Response(200, json={"stargazers_count": 1, "private": True})
        ),
    )
    with pytest.raises(ProviderError):
        await provider.fetch()


async def test_youtube_uses_official_raw_statistics_only():
    data = {
        "items": [
            {
                "id": "abcdefghijk",
                "snippet": {"title": "Public video", "publishedAt": "2025-01-01T00:00:00Z"},
                "statistics": {"viewCount": "1200", "likeCount": "30"},
            }
        ]
    }
    provider = YouTubeProvider(
        "test-only", ["abcdefghijk"], transport(lambda r: httpx.Response(200, json=data))
    )
    batch = await provider.fetch()
    assert not batch.entities[0].analytics_allowed
    assert {r.metric for r in batch.observations} == {"views", "likes"}
    assert batch.observations[0].metadata["retention_days"] == 29


async def test_youtube_missing_videos_and_statistics():
    provider = YouTubeProvider(
        "test-only", ["abcdefghijk"], transport(lambda r: httpx.Response(200, json={"items": []}))
    )
    batch = await provider.fetch()
    assert not batch.observations
    assert batch.warnings


async def test_transport_caches_and_does_not_retry_quota():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True})

    t = transport(handler)
    await t.json("https://api.github.com/repos/owner/repo")
    await t.json("https://api.github.com/repos/owner/repo")
    assert len(calls) == 1
    assert t.stats["cache_hits"] == 1
    t2 = transport(lambda r: httpx.Response(429, headers={"Retry-After": "120"}))
    with pytest.raises(RateLimited):
        await t2.json("https://api.github.com/repos/owner/repo")
    assert t2.stats["requests"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/repos/x/y",
        "https://localhost/admin",
        "https://api.github.com:8080/private",
        "https://secret@api.github.com/repos/x/y",
    ],
)
async def test_transport_rejects_nonallowlisted_urls(url):
    with pytest.raises(ProviderError, match="allowlisted"):
        await transport(lambda r: httpx.Response(200, json={})).json(url)


async def test_malformed_json_and_credentials_are_sanitized():
    for response in [
        httpx.Response(200, text="not json"),
        httpx.Response(401, text="sensitive key"),
        httpx.Response(302, headers={"Location": "http://localhost/private"}),
    ]:
        with pytest.raises(ProviderError) as error:
            await transport(lambda r, response=response: response).json(
                "https://api.github.com/repos/o/r", params={"key": "super-secret"}
            )
        assert "super-secret" not in str(error.value)
        assert "sensitive key" not in str(error.value)


async def test_timeout_retries_are_bounded(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr("trendforge.providers.base.asyncio.sleep", no_sleep)

    def fail(request):
        raise httpx.ReadTimeout("https://secret.example/?key=hidden")

    t = transport(fail)
    with pytest.raises(ProviderError, match="timed out") as error:
        await t.json("https://api.github.com/repos/o/r")
    assert t.stats["requests"] == 3
    assert "hidden" not in str(error.value)


async def test_provider_failure_does_not_block_other_sources(session, settings, batch):
    class Bad(TrendProvider):
        name = "bad"

        @property
        def configured(self):
            return True

        async def fetch(self):
            raise ProviderError("Temporarily unavailable")

    class Good(TrendProvider):
        name = "good"

        @property
        def configured(self):
            return True

        async def fetch(self):
            return batch

    result = await update(session, settings, adapters=[Bad(), Good()], force=True)
    assert result["analysis_failures"] == 0
    assert session.get(ProviderState, "bad").status == "OFFLINE"
    assert session.get(ProviderState, "good").status == "ONLINE"
    assert result["entities_recalculated"] == 1


async def test_not_configured_does_not_call_provider(session, settings):
    class Disabled(TrendProvider):
        name = "disabled"

        @property
        def configured(self):
            return False

        async def fetch(self):
            raise AssertionError("Must not fetch without configuration")

    await update(session, settings, adapters=[Disabled()])
    assert session.scalar(select(ProviderState)).status == "NOT CONFIGURED"


async def test_demo_history_is_deterministic_when_appended():
    short = await DemoProvider(datetime(2025, 2, 1, 23, 59, tzinfo=UTC)).fetch()
    long = await DemoProvider(datetime(2025, 2, 3, 23, 59, tzinfo=UTC)).fetch()

    def key(row):
        return (row.entity_id, row.metric, row.source_timestamp)

    old = {key(row): row.value for row in short.observations}
    new = {key(row): row.value for row in long.observations}
    assert all(value == new[k] for k, value in old.items())
    assert all(row.synthetic for row in long.observations)


async def test_successful_empty_youtube_refresh_removes_cached_videos(session, settings):
    from trendforge.db import Entity, Observation

    data = {
        "items": [
            {
                "id": "abcdefghijk",
                "snippet": {"title": "Public video"},
                "statistics": {"viewCount": "1200"},
            }
        ]
    }
    active = YouTubeProvider(
        "test-only", ["abcdefghijk"], transport(lambda r: httpx.Response(200, json=data))
    )
    await update(session, settings, adapters=[active], force=True)
    assert session.scalars(select(Observation)).first() is not None
    missing = YouTubeProvider(
        "test-only", ["abcdefghijk"], transport(lambda r: httpx.Response(200, json={"items": []}))
    )
    result = await update(session, settings, adapters=[missing], force=True)
    assert result["providers"][0]["status"] == "DEGRADED"
    assert session.scalars(select(Observation)).first() is None
    assert session.get(Entity, "youtube:abcdefghijk").name == "Unavailable YouTube video"
