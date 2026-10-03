# Security

The initial deployment is a single local research workspace. It is not a multi-tenant SaaS security boundary. Live mode requires a server API access token, but a token holder shares the same data/watchlist as other token holders.

Implemented controls include environment/SecretStr secrets, explicit data schemas, HTTPS provider allowlisting, identifier validation, bounded retries, response/time limits, safe error messages, ORM parameter binding, write-origin checks, per-process rate limits, no arbitrary-code endpoint, restricted Docker defaults and immutable forecast ledger triggers.

Before public exposure, add TLS and a trusted authenticated gateway; keep database ports private; configure allowed origins; rotate tokens; use a shared limiter when scaling; and avoid logging authorization headers or full provider URLs. Do not expose the default anonymous demo API with sensitive datasets attached.

## Reporting

After this repository is published, use GitHub's private vulnerability reporting feature if enabled, or privately contact its maintainers through the repository's security contact. Do not post working credentials, exploit details against a deployed private instance, or raw licensed datasets in public issues. No email address is invented in this project.

## Scans

The included security workflow runs dependency auditing, Bandit and secret-pattern/local-link checks. Pattern scanning is not proof that every secret is absent. Dependency findings depend on advisory availability at the time of scanning. Enable repository-host secret scanning when available and use least-privilege provider tokens.

Installed provider plugins execute Python code and must be trusted. Never load arbitrary plugin packages or pickle/joblib models from untrusted sources. Plugin activation requires explicit server configuration; it is not available through the browser API.

Backups must preserve ledger integrity while honoring provider retention restrictions. The database triggers stop normal update/deletion operations but are not tamper-proof against a database administrator.
