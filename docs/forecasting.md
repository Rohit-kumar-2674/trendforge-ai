# Forecasting

Forecasts are estimates, not investment recommendations or promises of virality. The enabled model is a transparent historical-analogue baseline; `AI` in the project name does not imply an LLM or a deep model.

## Separate meanings

| Label | Meaning |
|---|---|
| Observation | A stored metric/value from a specified source and timestamp |
| Analysis | A reproducible computation from observed values |
| Inference | A heuristic interpretation such as an accelerating lifecycle |
| Forecast | Estimated probabilities over mutually exclusive future outcomes |
| Confidence | Strength/limitations of the available evidence, not the largest class probability |

## Enabled baseline

1. Read one daily primary series from a single provider/unit.
2. Require at least 90 observations and enough data for the configured window/horizon.
3. Normalize a trailing 21-observation log pattern by historical changes.
4. Search older windows using a configured similarity measure. Their outcome periods must finish before the current query window starts.
5. Keep at most 20 sufficiently similar, mutually disjoint pattern-plus-outcome intervals. Require at least three; otherwise no probability is returned.
6. Define up/down using a symmetric threshold `max(0.01, trailing_return_std * sqrt(horizon) * 0.5)`. Everything between the boundaries is sideways.
7. Count classes and add a symmetric one-per-class prior: `p(class) = (count + 1) / (n + 3)`.

Financial defaults store 1/5/20 observed-session forecasts; general trends store 3/7/30 calendar-day forecasts. The research API supports horizons 1–30; the CLI supports 1–90 where history permits. Models are evaluated independently by horizon. A calendar month is not silently equated to a trading month.

Default production distance is Euclidean. Cosine, correlation and constrained DTW are available in the analogue engine. Browser research exposes the first three; expensive DTW exploration belongs in offline Python.

Wilson intervals describe historical analogue frequencies. They do not claim to be fully calibrated predictive confidence intervals. Overlapping windows are excluded, but remaining serial dependence, selection bias and regime changes can still invalidate a simple frequency interpretation.

## Confidence and out-of-distribution rules

The baseline can show only `LOW` or `VERY LOW` confidence. `LOW` requires at least eight analogues, average similarity of at least 0.55, data-quality score at least 85 and no OOD warning. Because it lacks a verified real-world calibration history, even a high agreement among analogues cannot produce `HIGH` confidence.

OOD checks compare recent mean/volatility and extreme returns with the earlier return distribution. This is a transparent heuristic, not a reliable detector of every unprecedented event. An OOD warning lowers confidence. Synthetic output always states that it has no real-world predictive validity.

## Audit and outcomes

The forecast log stores an immutable row with source as-of time, issue time, model version, horizon/unit, data/feature hashes, input vector and configuration. A separate outcome row is inserted once the future target is observed. Calendar targets require the exact date; missing values are not replaced with the next available day's outcome. Trading targets are subsequent observed sessions and must be interpreted with the documented calendar limitations.

Past forecasts are not deleted when wrong, replaced by a retrained model or recalculated when read. Run `trendforge verify-audit FORECAST_ID` to replay the stored snapshot under the recorded baseline implementation. Preserve old code releases to reproduce older future versions.

## What is deliberately absent

No projected stock-price line with fabricated precision, broker execution, guaranteed directional signal, six-state lifecycle probability model, LSTM, transformer or unvalidated model promotion. The future six-state trend forecast must define mutually exclusive outcomes before implementation; acceleration is not automatically an independent class from continued growth.
