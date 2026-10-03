# Architecture

TrendForge is a local research application with a separate ingestion process. The API performs bounded reads and local watchlist/research actions; provider refreshes run in the CLI or external scheduler, never a timer inside every API worker.

## Boundaries

| Layer | Responsibility | Code |
|---|---|---|
| Provider adapters | Credentials, transport, native response validation, normalized entities/observations | `backend/trendforge/providers/` |
| Schemas | Finite values, timezone-aware timestamps, safe provenance URLs | `backend/trendforge/schemas.py` |
| Storage | Entities, immutable observations by natural key, scores, forecasts, outcomes, providers, watchlist, reports, events, models | `backend/trendforge/db.py` |
| Pipeline | Provider failure isolation, deduplication, freshness, change hashes, outcomes | `backend/trendforge/pipeline.py` |
| Analysis | Causal derivatives, weights, anomaly and lifecycle rules, analogues and lead–lag | `backend/trendforge/trends/` |
| Forecasting | Baseline, confidence, purged validation, calibration experiments, registry gate | `backend/trendforge/forecasting/` |
| Delivery | REST/OpenAPI, Typer CLI, escaped HTML/Markdown/JSON reports | `main.py`, `cli.py`, `reports.py` |
| Frontend | React/TypeScript; fetches backend values, renders accessible SVGs, no provider secrets | `frontend/src/` |

## Identity and provenance

Entity IDs include a provider namespace (`av:IBM`, `github:owner:repo`, `youtube:VIDEO_ID`) or explicit `demo:` namespace. Names and keywords are searchable. An observation preserves provider, metric, value, unit, source timestamp, retrieval timestamp and synthetic flag. A uniqueness constraint deduplicates entity/provider/metric/time. The original value is retained when the same key is seen again; provider revision reconciliation is not yet implemented.

Primary series use one provider and one unit. Multiple intraday snapshots are reduced to the last recorded value on each UTC date. Values from unrelated providers are never silently stitched. Finance adapter source-date metadata preserves the original exchange date; UTC timestamp grouping is a display/analysis convention, not an exchange-calendar engine.

## Incremental processing

Retrieval caches at the provider level for the expected 24-hour interval. Observations insert only when their natural key is new. A score snapshot hash covers the primary series, secondary measurements, domain weights and engine version. Unchanged fingerprints skip score/forecast recomputation. This release still reads the full local series to hash it; it is not an incremental time-series database optimized for millions of entities.

## Forecast integrity

Forecasts retain generation time, source as-of time, horizon/unit, model version, data hash, feature hash, frozen numeric inputs and the feature/configuration snapshot. The API returns stored predictions, never silently recalculates old ones. SQLite/PostgreSQL migration triggers reject forecast and outcome updates/deletions. Administrators can alter the database; these controls are not a tamper-proof third-party attestation.

Outcomes live in a separate one-per-forecast table. Calendar horizons require the exact target date. Trading horizons count subsequent observed sessions and are labeled accordingly; missing exchange sessions cannot be fully distinguished from holidays without an exchange calendar. Outcomes with source timestamps at or before issuance are never counted as prospective successes.

The baseline card is versioned. Research metrics append to `model_metrics`. Promotion eligibility requires a sufficiently sized, same-ID, prospective real-data holdout plus improved metrics and passed checks. This version never automatically promotes a candidate.

## Operating scope

SQLite, one API process and a single local workspace are the default. The watchlist is workspace-wide, not isolated per logged-in user. Server access tokens are supported; account management, multi-tenant authorization and distributed quotas are not. Deploy behind TLS and an authenticated gateway if exposing beyond localhost. PostgreSQL configuration and migrations are provided but need an actual server smoke test in the target environment.

The relationship table is a future persistence boundary; the current correlation explorer computes results on demand and does not fabricate a populated knowledge graph. No hidden model or background LLM call exists.
