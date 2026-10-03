# Providers and data rights

Provider interfaces return `ProviderBatch(entities, observations, warnings)`. A provider can be unconfigured without crashing the application. An HTTP error never leads to secret scraping or silently substituted synthetic values.

| Provider | Configuration | Data returned | Analytics/retention |
|---|---|---|---|
| Demo | `DEMO_MODE=true` | Deterministic synthetic history across six domains | Clearly labeled; no real-world claims |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY`, `FINANCE_SYMBOLS` | Compact raw daily OHLCV | Unadjusted; corporate actions may distort results; verify plan and redistribution rights |
| GitHub REST | `GITHUB_REPOS`, optional `GITHUB_TOKEN` | Public repository stars/forks/open issues | Current snapshots only; daily history begins when collected |
| YouTube Data API | `YOUTUBE_API_KEY`, `YOUTUBE_VIDEO_IDS` | Raw public video view/like/comment counts when returned | Custom scores and forecasts disabled; raw statistics expire after 29 days |
| Google Trends | No generally configured adapter | None | NOT CONFIGURED; a flag does not confer access |

External adapters are covered by mocked contract/failure tests. No real credentials were available during the initial build, so successful live API calls are not claimed. The transport does not log request URLs, API keys or provider response bodies.

## Finance

The adapter requests `TIME_SERIES_DAILY` with `outputsize=compact`. It checks provider-level error, quota and plan messages even when HTTP returns 200. Missing, malformed or inconsistent OHLC rows are skipped with a degraded status. Dates use the provider's exchange timezone. Because the response gives a date rather than an exact tick timestamp, the adapter conservatively assigns 23:59 exchange-local time and excludes a day until that timestamp is in the past. Original date and timezone remain in provenance.

The adapter does not assert that all Indian equities, commodities, crypto, indices or ETFs are supported by every account. Enter only symbols your provider supports. Quote currency is marked for verification rather than guessed from the ticker. Prices are not split/dividend adjusted. No symbol universe, delisted-security archive or survivorship-free backtest is bundled.

## GitHub

Only explicitly configured public `owner/repository` identifiers are fetched. Private repositories are rejected even if a token could access them. Stored fields are repository-level counters, not individual stargazers or user profiles. Current counters do not become a fabricated historical star chart. The source also records repository creation time; the detail payload distinguishes net stars in the latest interval, elapsed-day velocity and lifetime average.

After enough snapshots, the baseline forecasts the **cumulative star count**. It does not pretend to forecast daily adoption independently from that counter. Unstars may reduce the count. Distinguishing accelerating daily adoption from a monotonically growing counter is a future target-model improvement.

## YouTube

The default Data API rules restrict new/derived metrics and storage of non-authorized statistics. Additional permissions for audited analytics clients are a separate process. This release therefore keeps live API data raw-only, excludes it from scoring, forecasting and correlation, and purges old statistics at 29 days on startup/update. Read paths exclude expired raw observations even when the updater has not run. Metadata is cleared when no retained observations remain.

API-backed counts must not be confused with synthetic creator-topic examples. Raw YouTube snapshots are excluded from archival reports and the supplied GitHub artifact workflow. A successful API response that omits previously configured videos removes their cached raw observations, including when every requested video is unavailable. Operators are responsible for ensuring backups do not keep expired raw API data and for honoring removals. A public YouTube API client also needs the required user consent, terms and privacy disclosures; the local research adapter is not a certification that an arbitrary deployment is policy compliant. This version has no OAuth owner authorization or extra derived-metric approval flow.

The request obtains only explicitly configured video IDs. It does not crawl comments, channels, private accounts or transcripts. No likes, comments or uploads are sent.

## Failure, caching and fallback

Each provider has its own commit boundary. One provider can fail while others complete. The previous dataset remains available with its original source timestamp. A 24-hour persistent provider cache prevents needless refreshes; transport responses also have a small in-run TTL. HTTP calls use HTTPS host allowlisting, fixed timeouts, bounded exponential retries with jitter and no automatic redirects. A quota response defers the provider immediately rather than repeatedly retrying it.

Current statuses: `ONLINE`, `DEGRADED`, `RATE LIMITED`, `STALE`, `OFFLINE`, `NOT CONFIGURED`. Capability labels distinguish `OPTIONAL`, `MOCK/DEMO` and disabled access. There is no real-time feed in v0.1; `LIVE PROVIDERS` means actual configured provider data, not real-time ticks.

Multi-provider arbitration, automatic provider disagreement reconciliation and licensed retail/search feeds are roadmap work. Do not mix feeds merely because their entity labels look similar.

## Official reference links

- [Alpha Vantage documentation](https://www.alphavantage.co/documentation/)
- [YouTube videos.list](https://developers.google.com/youtube/v3/docs/videos/list)
- [YouTube developer policies](https://developers.google.com/youtube/terms/developer-policies), especially storage and derived-data sections
- [GitHub repository endpoint](https://docs.github.com/en/rest/repos/repos#get-a-repository)
- [GitHub rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)

Review current terms before enabling or publicly deploying a provider. Code licensing never grants rights to redistribute a third party's data.
