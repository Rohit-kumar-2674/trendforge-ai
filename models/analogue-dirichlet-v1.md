# Model card: analogue-dirichlet-v1

| Field | Value |
|---|---|
| Model | Historical analogue outcome frequency with symmetric Dirichlet prior |
| Release | 0.1.0 |
| Status | Enabled experimental baseline |
| Feature set | Normalized trailing 21-observation log pattern |
| Training range | Entity history available at each forecast issuance; frozen in the audit snapshot |
| Output | Up / sideways / down, mutually exclusive, sum to 1 |
| Default horizons | Finance: 1/5/20 observed sessions; other domains: 3/7/30 calendar days |
| Similarity | Euclidean by default; minimum similarity 0.35; max 20 matches |
| Leakage controls | Analogue outcome before query start; disjoint analogue intervals; causal features |
| Prior | One pseudo-observation per class |
| Sideways threshold | max(1%, trailing 60-return standard deviation × sqrt(horizon) × 0.5) |
| Calibration | Unvalidated live probabilities; reliability infrastructure available |
| Confidence cap | LOW |
| Performance | No verified prospective real-world accuracy claim |
| Promotion | No automatic promotion |

## Intended use

Reproducible research, understanding changes, investigating evidence, comparing methods, and building a transparent forecast-outcome history. Not personalized investment advice, automated trading, or guaranteed virality prediction.

## Limitations

Historical resemblance is neither causality nor a guarantee of future behavior. Independent analogue samples are small, financial data may be unadjusted/revised, available entities may have survivorship bias, and label thresholds encode a modeling choice. Source quality and freshness vary. Synthetic series exercise software behavior only. Numeric patterns omit many real drivers such as earnings, macro conditions, product launches, promotions and external shocks.

Production status in the registry means this is the currently enabled method; it does not certify predictive performance. Unknown or poorly matched conditions reduce confidence or withhold probabilities.

## Reproducibility fields

Every forecast stores model version, issue/as-of time, horizon/unit, input timestamps and values, provider/unit, features, configuration, snapshot hash and feature hash. The corresponding outcome is stored separately. Preserve this model implementation alongside the ledger for replay.
