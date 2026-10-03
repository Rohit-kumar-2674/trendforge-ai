# Synthetic demo dataset

**Every value is synthetic.** The dataset does not describe current markets, actual platform counts or real-world forecast performance.

`catalog.json` lists the demo entities and generator metadata. `sample_observations.jsonl` is a compact inspectable sample; it is not used as hidden prediction output. The complete executable generator is `backend/trendforge/providers/demo.py`.

The generator starts on 2025-01-01, uses stable entity seeds, and combines fixed periodic behavior, domain-specific drift and seeded noise. Fictional financial entities omit weekends; they are not a complete exchange-calendar simulation. Every row is labeled `provider=demo` and `synthetic=true`. A repeat run adds no duplicate observation keys and leaves existing historical values intact.

Use `python -m trendforge demo` to create current demo history, compute the actual engine outputs, store forecasts and generate the report. No forecast probabilities are hardcoded in these data files.
