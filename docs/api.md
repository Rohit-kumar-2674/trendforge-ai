# REST API

Base URL: `http://127.0.0.1:8000`. Swagger/OpenAPI: `/docs` and `/openapi.json`. The frontend development server proxies `/api` to the backend. Nginx provides the equivalent same-origin proxy in Docker.

When `API_TOKEN` is set, API requests except health require `Authorization: Bearer <workspace-token>`. Live mode refuses to start without that token. Provider keys never leave the server. This is a single-workspace token, not a multi-user account system. Reverse proxies must add TLS and appropriate access controls for public exposure.

| Method | Route | Behavior |
|---|---|---|
| GET | `/api/system/health` | Database reachability, version, active mode, UTC clock |
| GET | `/api/system/metrics` | Dataset/forecast counts and provider request summaries |
| GET | `/api/trends?q=&domain=&region=&sort=` | Search and discovery over configured entities |
| GET | `/api/trends/emerging` | Early-signal ordering |
| GET | `/api/trends/accelerating` | Acceleration ordering |
| GET | `/api/trends/{id}` | Entity, score, freshness, latest preferred forecast and timeline |
| GET | `/api/trends/{id}/history` | Actual observed series and recorded score snapshots |
| GET | `/api/trends/{id}/forecast` | Up to 100 stored forecast records and separate outcomes |
| GET | `/api/trends/{id}/analogues` | Analogues used for the preferred stored horizon |
| GET | `/api/trends/{id}/evidence` | Recent raw observations and provenance; configurable limit ≤2,000 |
| GET | `/api/forecasts/{id}/audit` | Full frozen input/features/configuration snapshot |
| GET | `/api/stocks/{ticker}` | First configured financial match; use canonical IDs for precision |
| GET | `/api/stocks/{ticker}/forecast` | Stored forecasts for that financial match |
| GET | `/api/youtube/topics` | Synthetic topics or configured raw public videos, according to mode |
| GET | `/api/search/topics` | Synthetic search examples; live capability is NOT CONFIGURED |
| GET/POST | `/api/watchlist` | List or save a workspace entity |
| DELETE | `/api/watchlist/{id}` | Remove that entity from the watchlist |
| GET | `/api/providers/status` | Provider health, configuration instructions and retrieval metadata |
| GET | `/api/events` | Recorded threshold/anomaly/lifecycle events |
| GET | `/api/models` | Versioned model cards |
| GET | `/api/models/track-record` | Prospective performance with pending counts and breakdowns |
| GET | `/api/relationships?left=ID&right=ID` | Exploratory lead–lag analysis of aligned log changes |
| POST | `/api/experiments/backtest` | Bounded retrospective research; never changes production |
| GET | `/api/reports` | Report archive metadata |
| GET | `/api/reports/{id}?format=json\|md\|html` | Download a saved report |

Watchlist request:

```json
{"entity_id": "demo:smart-glasses"}
```

Research request:

```json
{"entity_id": "demo:smart-glasses", "horizon": 7, "window": 21, "method": "euclidean"}
```

Trend results contain separate `score`, `forecast`, `freshness` and `synthetic` fields. A missing forecast is unavailable data, not a zero-percent probability. Source and retrieval timestamps are ISO 8601 UTC. UI date formatting always labels UTC.

No HTTP update-provider or execute-code endpoint exists. Ingestion is an explicit CLI/scheduler action. The built-in rate limiter is per-process, intended for a local single-worker deployment; use a shared limiter before horizontal scaling. API responses default to `Cache-Control: no-store`.
