from importlib.metadata import entry_points

from trendforge.config import Settings
from trendforge.providers.base import ProviderBatch, TrendProvider
from trendforge.providers.demo import DemoProvider
from trendforge.providers.finance import AlphaVantageProvider
from trendforge.providers.github import GitHubProvider
from trendforge.providers.youtube import YouTubeProvider


class DisabledSearchProvider(TrendProvider):
    name = "google_trends"
    capability = "NOT CONFIGURED"
    instructions = "No generally configured search provider. Add an approved, licensed SearchTrendProvider through the SDK; enabling the flag alone does not grant API access."

    @property
    def configured(self) -> bool:
        return False

    async def fetch(self) -> ProviderBatch:
        return ProviderBatch()


def providers(settings: Settings) -> list[TrendProvider]:
    def csv(value: str) -> list[str]:
        return [x.strip() for x in value.split(",") if x.strip()]

    live: list[TrendProvider] = [
        AlphaVantageProvider(
            settings.alpha_vantage_api_key.get_secret_value(), csv(settings.finance_symbols)
        ),
        YouTubeProvider(
            settings.youtube_api_key.get_secret_value(), csv(settings.youtube_video_ids)
        ),
        GitHubProvider(csv(settings.github_repos), settings.github_token.get_secret_value()),
        DisabledSearchProvider(),
    ]
    enabled = csv(settings.provider_plugins)
    registered = {entry.name: entry for entry in entry_points(group="trendforge.providers")}
    for name in enabled:
        if name not in registered:
            raise ValueError(f"Provider plugin is not installed: {name}")
        adapter = registered[name].load()(settings)
        if not isinstance(adapter, TrendProvider):
            raise TypeError(f"Invalid TrendProvider plugin: {name}")
        if adapter.name in {p.name for p in live} | {"demo"}:
            raise ValueError(f"Duplicate provider name: {adapter.name}")
        live.append(adapter)
    return [DemoProvider(), *live] if settings.demo_mode else live
