# Adding a domain or provider

The engine depends on normalized entities/observations, not a third-party API response. A new provider does not need changes to scoring or forecasting. Start with a small, legitimate source whose timestamp, licensing, unit and update cadence are clear.

## Provider plugin interface

Subclass `TrendProvider` and implement `configured` and `async fetch() -> ProviderBatch`. Return `EntityInput` and `ObservationInput` objects; invalid or naive timestamps are rejected by the schema. A plugin receives server `Settings`, so read only the secrets/configuration it actually requires. Installed plugins are trusted Python packages, not untrusted user code submitted through the API.

Register a factory in your package's `pyproject.toml`:

```toml
[project.entry-points."trendforge.providers"]
my_provider = "my_package:create_provider"
```

The factory takes `Settings` and returns a `TrendProvider`. Install the package explicitly, then set `PROVIDER_PLUGINS=my_provider`. Plugins are opt-in. Unknown names, wrong base classes and duplicate provider names fail configuration rather than silently shadowing a built-in source. Never enable packages from untrusted repositories.

The built-in HTTP transport accepts only its fixed provider hosts. For a new provider, implement a similarly restrictive transport in the installed adapter; do not turn a user-supplied URL into an unrestricted server-side HTTP request. Disable redirects, validate identifiers, set response/time limits, redact errors and implement bounded retries.

## Data requirements

- Canonical IDs need stable namespaces; never map two similar display names to one asset without evidence.
- Every observation includes actual source time, retrieval time, metric, value, unit, provider and synthetic status.
- Do not convert cumulative counters into fabricated historical daily values. Collect snapshots over time or obtain a licensed history.
- Declare `analytics_allowed=False` when source policies do not permit derived metrics.
- Keep categories/keywords focused on aggregate public topics. No personal-location tracking or hidden-identity resolution.
- Add mock response, malformed payload, empty response, quota, timeout, timezone, duplicate and privacy/provenance tests.

## Scoring a new domain

Use the `general` domain first or extend the `Domain` enum with an explicit API/frontend mapping. Add weights to [weights.yaml](../backend/trendforge/config/weights.yaml). The current engine only uses components it actually computes; defining a YAML key alone does not implement a new feature. Missing components remain unavailable and reduce weight coverage.

Version the engine when formulas change. Keep source metric meaning, timebase, thresholds and model feature names in documentation. Test that appending future samples cannot alter a historical prefix. Never automatically promote a new model based on the same data used to choose it.

## Extensibility limits

Provider entry points are implemented. A stable public entry-point SDK for arbitrary scorers/models, semantic clustering, Neo4j and marketplace discovery remains roadmap work. Existing research functions can be called from a separate experiment without modifying the production registry.
