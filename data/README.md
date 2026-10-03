# Data

`trendforge.db` is created locally and ignored by Git. Provider keys and real datasets never belong in the source repository.

The [demo directory](demo/README.md) contains a small synthetic sample and catalog. The executable demo generator creates the full dataset reproducibly from a fixed start date and per-entity seeds; running it later appends the same deterministic history rather than rewriting old values.

All observations have source/retrieval timestamps, provider, metric, value, unit and a synthetic flag. Backing up live databases or exporting forecast audit snapshots can carry third-party data restrictions; review the provider license and expiry requirements first.
