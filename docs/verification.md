# v0.1 verification report

Verified on **2026-09-30 UTC** in Linux with Python 3.12.14, Node 24.19.0, SQLite and Chromium. This records checks actually performed; it is not a claim of production readiness or predictive validity.

| Check | Result | Scope |
|---|---|---|
| Python tests | **81 passed** | Analysis, forecasting, leakage, calibration, database migrations, provider mocks, API, reports, timestamps, freshness and audit protection |
| Python lint/format | **Passed** | Ruff; 45 Python files across backend, tests and scripts |
| Python types | **Passed** | mypy; 30 application source files |
| Frontend lint/types | **Passed** | ESLint and TypeScript |
| Frontend production build | **Passed** | Vite; approximately 284 KB JS and 40 KB CSS before compression |
| Browser workflows | **4 passed** | Desktop 1512×1080 and Android emulation 412×915; real API and Vite servers |
| Fresh SQLite demo | **Passed** | Alembic creates schema; 16 entities, 31,668 observations, 48 forecasts; zero analysis failures |
| Repeat demo ingestion | **Passed** | Zero inserted duplicates and zero unchanged entities recalculated; existing forecasts preserved |
| Frozen forecast replay | **Passed** | Stored feature hash and exact baseline probabilities match |
| Reports | **Passed** | Timestamped Markdown, JSON and escaped HTML; browser JSON download; live/demo isolation |
| API startup/docs | **Passed** | Uvicorn startup and health through browser tests; `/docs` and OpenAPI through integration tests |
| Python dependency audit | **No known vulnerabilities reported** | `pip-audit` on runtime lock, 43 packages, at audit time |
| Node dependency audit | **No known vulnerabilities reported** | `npm audit --omit=dev`, at audit time |
| Source security scan | **Passed** | Bandit medium/high severity gate; no findings in the scanned application files |
| Repository checks | **Passed** | Local documentation links, workflow YAML structure, common secret patterns and container configuration checks |
| Docker | **Static review only** | Compose YAML and Dockerfile paths/security settings checked; no Docker executable/daemon available for build or startup |
| PostgreSQL | **Not exercised** | SQLAlchemy configuration and migrations supplied; no PostgreSQL service available here |
| External providers | **Mock-tested only** | Alpha Vantage, YouTube and GitHub response/error paths; no credentialed live contract validation |
| GitHub Actions | **Locally inspected only** | Five workflow files; no published repository or remote workflow runs |

Browser tests cover catalogue search, opening details, probability panels, historical analogues, provenance, saving a watchlist, provider status, lead–lag comparison, a walk-forward experiment, reliability bins, report download, mobile navigation and keyboard focus. Screenshots in this directory were captured from the running application. A regression assertion compares document width to the requested viewport, preventing the mobile page from silently widening around a scrollable table.

Leakage tests append extreme future observations and assert unchanged historical features, require training labels to finish before validation starts, and verify disjoint analogue outcomes and forecast targets. Research model targets remain non-overlapping across fold boundaries even when the horizon does not divide the fold size. Forecast and outcome update/delete attempts are rejected by SQLite triggers.

Provider tests include malformed JSON, empty data, invalid identifiers, authorization errors, quota limits, retries, timeouts, duplicates, timezone normalization, missing data, unavailable videos and isolation of unrelated provider failures. Raw-only YouTube statistics are excluded from archival reports and forecasts.

The clean-run prospective ledger correctly starts with **48 pending and zero resolved forecasts**. These are computed from synthetic series, not fabricated real-market forecasts or historical success claims. No measured live accuracy, calibration quality or profitable strategy is asserted.

On **2026-10-03 UTC**, lint, formatting, types and repository checks passed again. The current restricted runner stalled when Starlette TestClient dispatched to its background event loop; a standalone AnyIO portal with no TrendForge imports reproduced the stall. The four TestClient cases therefore could not be rerun in that environment; the remaining **77 tests passed** in the final rerun. The complete 81-test pass and four browser passes above are the recorded September audit of the same application code. The September screenshots and clean-demo counts retain their original observation dates.

## Reproduce

Use the installation and validation commands in the [README](../README.md). Run `python -m trendforge demo` before browser tests. Browser tests use a local workspace and may add a watchlist entry. Install Playwright Chromium through its standard install command on your development machine. This audit used an explicitly supplied compatible Chromium binary because the default browser download was unavailable in the execution environment.

An upstream Starlette/httpx TestClient deprecation warning was emitted; tests completed successfully. No warning was suppressed to obtain a passing test result.

## Remaining verification

Before a live deployment, run actual provider contract checks with authorized credentials, build/start both Docker profiles, test PostgreSQL migrations and ledger triggers, exercise backups/restores, and verify the scheduled workflows on the intended GitHub repository. Android results are browser emulation, not a physical-device or Termux installation test. The supplied mobile setup documents that limit.

The [roadmap](../ROADMAP.md) distinguishes implemented features from later news/search/fashion integrations, expanded model governance and advanced inference. Baseline probabilities remain unvalidated and confidence is capped conservatively.
