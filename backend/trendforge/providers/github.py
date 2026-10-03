import re

from trendforge.providers.base import ProviderBatch, ProviderError, Transport, TrendProvider
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow


class GitHubProvider(TrendProvider):
    name = "github"
    instructions = "Set GITHUB_REPOS=owner/repo,...; GITHUB_TOKEN is optional for public repositories. Snapshots accumulate daily."

    def __init__(
        self, repos: list[str], token: str = "", transport: Transport | None = None
    ) -> None:
        super().__init__(transport)
        self.repos = repos[:20]
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.repos)

    async def fetch(self) -> ProviderBatch:
        batch = ProviderBatch()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for repo in self.repos:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repo):
                raise ProviderError("Expected an owner/repository identifier")
            data = await self.transport.json(
                f"https://api.github.com/repos/{repo}", headers=headers
            )
            if "stargazers_count" not in data or data.get("private", False):
                raise ProviderError("Repository is unavailable or not public")
            slug = repo.lower().replace("/", ":")
            entity = EntityInput(
                id=f"github:{slug}",
                name=repo,
                domain=Domain.TECHNOLOGY,
                category="Open source",
                keywords=[repo, *data.get("topics", [])[:20]],
                primary_metric="stars",
                unit="stars",
                cadence="calendar_day",
            )
            batch.entities.append(entity)
            now = utcnow()
            for metric, key in [
                ("stars", "stargazers_count"),
                ("forks", "forks_count"),
                ("issues", "open_issues_count"),
            ]:
                if key in data:
                    batch.observations.append(
                        ObservationInput(
                            entity_id=entity.id,
                            provider=self.name,
                            metric=metric,
                            value=data[key],
                            source_timestamp=now,
                            retrieved_at=now,
                            source_url=f"https://github.com/{repo}",
                            unit="count",
                            metadata={
                                "created_at": data.get("created_at"),
                                "metric_kind": "cumulative_counter",
                                "snapshot_only": True,
                            },
                        )
                    )
        return batch
