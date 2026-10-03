# Research notebooks

Use this directory for independent research notebooks, not production data-processing logic. The runnable experiment interface is already available in the dashboard and CLI:

```bash
trendforge evaluate demo:smart-glasses --horizon 7
trendforge evaluate demo:orbital --horizon 5 --ensemble
```

Keep notebook outputs explicitly labeled by data mode. Do not commit real-provider datasets, API keys, future-derived features or cherry-picked performance charts. Promote reusable, tested research code into the backend only after chronological validation and review.
