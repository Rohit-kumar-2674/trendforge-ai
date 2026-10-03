# Trend engine

Scores are heuristic indices on 0–100. They are not probabilities and are not validated economic indicators. Domain weights live in [weights.yaml](../backend/trendforge/config/weights.yaml), not in the dashboard.

## Causal features

Trailing EMA, SMA and rolling-median smoothing use only the current and previous samples. The optional polynomial smoother evaluates the endpoint of each trailing window; it does not use a centered Savitzky–Golay filter that would incorporate future observations. LOESS is not included.

Velocity divides change in the smoothed value by actual elapsed calendar days. Acceleration differences those velocities with the corresponding elapsed intervals; jerk differences acceleration. The output labels the unit. Separately, relative acceleration compares the latest seven-observation percentage change with the preceding seven-observation change. Seven trading observations are not seven calendar days.

Momentum and acceleration are mapped through bounded hyperbolic-tangent transforms relative to a volatility-aware scale. Persistence is the fraction of positive recent changes. Robust return anomalies use the median and MAD of earlier returns, excluding the current return from the baseline. Source diversity is zero for one independent source: three metrics from the demo generator do not count as three confirmations.

Search, engagement and volume components are included only when actually observed. Missing breadth, sentiment, geography and other inputs remain `null`, their weights are excluded, and remaining weights are renormalized. Effective weights and coverage are exposed. The novelty component is a numerical high-water-mark proxy, explicitly not a semantic claim that an idea has never existed.

## Lifecycle, early warning and saturation

Lifecycle rules combine recent growth, acceleration, persistence, historical peak and baseline. Supported outcomes include Emerging, Early Growth, Accelerating, Breakout, Mainstream, Mature, Peaking, Cooling, Declining, Dormant and Resurgent. Thresholds are transparent in `trends/lifecycle.py`; they require domain-specific validation before use as a business decision rule.

Early-signal/breakout indices combine acceleration, persistence, a novelty proxy and source diversity, with a saturation penalty. The initial early and breakout score use the same conservative heuristic and are not two independently validated models. Saturation uses deceleration and elevated historical levels; creator oversupply and engagement-per-item are unavailable without appropriate sources.

Seasonality reports exploratory autocorrelations only after at least three cycles. It does not automatically seasonally adjust growth or prove a breakout is nonseasonal. Annual recurrence requires sufficient annual history, which the initial demo does not yet have.

## Quality and freshness

Quality checks flag nonfinite/negative values, duplicate times, expected-day gaps, large changes and insufficient samples. Exchange holidays can resemble missing sessions; the quality output says so. The ingestion schema requires explicit timezones and source times no later than retrieval. Provider currencies are never guessed or mixed.

Freshness uses the source timestamp, not just the most recent successful API call. There is no `LIVE` realtime status in this release. Stale observations remain visible and do not silently acquire today's date.

## Related-series research

The correlation explorer aligns UTC dates without forward filling, transforms levels to log changes, and searches ±14-day lags by default. Positive lag means the left series leads the right. The displayed uncertainty interval is a naive Fisher interval, does not correct for autocorrelation or multiple lag searches, and is labeled exploratory. Correlation does not establish causation.
