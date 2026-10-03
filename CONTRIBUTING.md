# Contributing

Start with a concrete research question, a bug reproduction, or a documented provider contract. Read [architecture](ARCHITECTURE.md), [provider guidelines](docs/adding-a-domain.md) and [evaluation rules](docs/model-evaluation.md).

Use a feature branch. Install the development lock, run the Python tests/types/lint, and build/test the frontend. Include a migration for persistent schema changes. Document whether external calls were tested against a live API or only mock fixtures; never call mock success a live integration test.

Preserve these invariants:

- Synthetic data must remain unmistakably synthetic through exports and screenshots.
- No random time-series splitting, future-aware smoothing or labels in features.
- An unavailable input is `null`/unavailable, not a made-up score or average.
- Metrics from one origin do not establish independent source diversity.
- Forecast rows cannot be edited after issuance; outcomes append separately.
- API keys stay in server environment variables; logs and test fixtures contain no secrets.
- Provider permissions and storage/redistribution restrictions apply to backups and audit snapshots too.
- Avoid unnecessary deep-model/dependency additions; demonstrate a concrete improvement before proposing one.

Use the issue templates and include relevant environment details. Tests should fail for a real error in behavior, especially temporal leakage or provenance, rather than merely mirror lines of implementation. The MIT license applies to contributions to the code; do not contribute provider data you cannot license.
