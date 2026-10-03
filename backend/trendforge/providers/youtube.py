import re

from trendforge.providers.base import ProviderBatch, ProviderError, Transport, TrendProvider
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow


class YouTubeProvider(TrendProvider):
    name = "youtube"
    instructions = "Set YOUTUBE_API_KEY and YOUTUBE_VIDEO_IDS. Raw public statistics only; custom scores/forecasts are disabled for API data under default developer policies."

    def __init__(self, key: str, ids: list[str], transport: Transport | None = None) -> None:
        super().__init__(transport)
        self.key = key
        self.ids = ids[:50]

    @property
    def configured(self) -> bool:
        return bool(self.key and self.ids)

    async def fetch(self) -> ProviderBatch:
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{11}", item) for item in self.ids):
            raise ProviderError("Invalid YouTube video ID")
        data = await self.transport.json(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(self.ids), "key": self.key},
        )
        if not isinstance(data.get("items"), list):
            raise ProviderError("YouTube returned an invalid items response")
        batch = ProviderBatch()
        for item in data["items"]:
            try:
                video_id = item["id"]
                if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                    raise ValueError("Invalid returned ID")
                snippet, stats = item["snippet"], item["statistics"]
                entity = EntityInput(
                    id=f"youtube:{video_id}",
                    name=snippet["title"][:200],
                    domain=Domain.YOUTUBE,
                    category="YouTube public video",
                    primary_metric="views",
                    unit="views",
                    analytics_allowed=False,
                )
                rows = []
                now = utcnow()
                for metric, key in [
                    ("views", "viewCount"),
                    ("likes", "likeCount"),
                    ("comments", "commentCount"),
                ]:
                    if key in stats:
                        rows.append(
                            ObservationInput(
                                entity_id=entity.id,
                                provider=self.name,
                                metric=metric,
                                value=stats[key],
                                source_timestamp=now,
                                retrieved_at=now,
                                source_url=f"https://www.youtube.com/watch?v={video_id}",
                                metadata={
                                    "published_at": snippet.get("publishedAt"),
                                    "channel_id": snippet.get("channelId"),
                                    "retention_days": 29,
                                    "raw_statistics_only": True,
                                },
                            )
                        )
                batch.entities.append(entity)
                batch.observations.extend(rows)
            except (KeyError, TypeError, ValueError):
                batch.warnings.append("Skipped an invalid or unavailable video")
        if len(batch.entities) < len(self.ids):
            batch.warnings.append("Some requested videos were unavailable")
        return batch
