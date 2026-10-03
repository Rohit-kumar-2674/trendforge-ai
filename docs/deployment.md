# Deployment, schedules and backups

## Local startup

`trendforge demo` initializes a deterministic dataset, runs analysis and generates reports. `trendforge serve` starts only the API. In live mode, `trendforge update` retrieves the configured sources. This separation prevents multiple API workers from each launching the same scheduled job.

The server defaults to 127.0.0.1. Docker exposes the UI and API on host localhost only. A browser refresh reloads saved results; it does not trigger a quota-consuming API refresh. Every result retains its original source timestamp and generated-at time.

## Docker and PostgreSQL

```bash
docker compose up --build
docker compose exec backend trendforge doctor
docker compose exec backend trendforge update
```

Both application containers run as non-root and use read-only root filesystems plus writable named data/report volumes. SQLite works with one API worker for the local workspace. Avoid multiple independent writers and use a persistent deployment lock around scheduled ingestion. PostgreSQL is supported through SQLAlchemy and the optional compose override; run a migration/insertion smoke test in the intended deployment before claiming production readiness.

The backend dependency lock includes the PostgreSQL driver. A strong `POSTGRES_PASSWORD` must be set for the override. Do not include URL-reserved characters in the password without encoding the DATABASE_URL appropriately. The database is not published on a host port by the supplied compose file.

## Daily GitHub workflow

`daily-update.yml` runs at **01:17 UTC** (06:47 India time) and supports manual dispatch. GitHub schedules are best effort, can be delayed, run on the default branch, and must be enabled in the published repository. Creating workflow files locally does not activate a remote job.

Each run:

1. Installs locked dependencies.
2. Restores the newest `trendforge-state` artifact from prior runs.
3. Ingests new provider observations, validates/deduplicates, calculates changed scores, creates eligible forecasts, and records mature outcomes.
4. Generates timestamped Markdown, JSON and HTML reports.
5. Uploads the cumulative SQLite ledger and report artifacts.

The daily and weekly workflows share a non-canceling concurrency group. They do not commit datasets or secrets into source control. The restore helper refuses to initialize a blank database if earlier successful work exists but its state artifact has expired or vanished. This avoids quietly losing the forecast track record.

**Public repositories run synthetic data only** in the supplied workflows. Live data artifacts are restricted to private repositories and still require appropriate provider storage/redistribution rights. Set repository variable `TRENDFORGE_DEMO_MODE=false`, `FINANCE_SYMBOLS`, `GITHUB_REPOS` and corresponding secrets only after reviewing those rights. A daily public-source GitHub repository snapshot can be obtained with the runner token or a suitably restricted token; do not grant broader scopes than necessary.

Raw YouTube API data is intentionally not configured in the artifact-producing workflow. Retention-limited raw data should be collected only in an appropriately maintained local/private service with compliant deletion and backup policies.

State artifacts have a 90-day retention setting. Each successful run rolls forward the entire cumulative ledger, but artifacts are not a permanent backup if automation stops. For reliable long-term operation, prefer PostgreSQL/SQLite on persistent storage, an external scheduler and tested backups over an artifact-only system.

## Weekly evaluation

`weekly-model-evaluation.yml` runs Sundays at 03:47 UTC. It restores the same state, replays the baseline, compares research ML models, exports prospective metrics and appends the research evaluation records. Set `EVALUATION_ENTITY` to a configured canonical ID when using live mode. It never automatically promotes a model, never overwrites old metrics, and never interprets synthetic accuracy as evidence of real predictive value.

The default weekly entity exists only in demo mode. If the configured live entity does not exist, the run fails visibly instead of pretending evaluation succeeded.

## VPS scheduling

Use cron/systemd or your platform's scheduler to run `trendforge update` from the repository root with its environment available. A simple cron schedule can invoke the venv binary directly; make sure the working directory and lock are explicit. Store logs without request bodies, API keys or credential-bearing URLs. Use one scheduler per database.

SQLite backups should use the database backup API or be taken while writers are stopped. Copying a database during a write can lose consistency. Preserve the code release and dependency locks with model snapshots. Do not retain expired provider data merely because it is in a backup.

## Beyond localhost

Before external deployment, use HTTPS, an authenticated gateway, explicit allowed origins, a strong `API_TOKEN`, managed secrets, appropriate provider permissions and private storage. The built-in watchlist is shared by the workspace; there is no multi-user access isolation. The in-memory IP rate limiter is per process and does not replace a shared gateway rate limiter. No claim of Internet-scale hardening is made for this MVP.
