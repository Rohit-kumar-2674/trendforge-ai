from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/trendforge.db"
    demo_mode: bool = True
    api_token: SecretStr = SecretStr("")
    alpha_vantage_api_key: SecretStr = SecretStr("")
    youtube_api_key: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    finance_symbols: str = "IBM"
    github_repos: str = ""
    youtube_video_ids: str = ""
    google_trends_enabled: bool = False
    provider_plugins: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
    reports_dir: Path = Path("reports")
    domain_weights_path: Path | None = None
    request_limit_per_minute: int = Field(default=180, ge=1, le=10000)


def get_settings() -> Settings:
    return Settings()
