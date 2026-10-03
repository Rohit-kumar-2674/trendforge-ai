# Stock intelligence

The financial adapter supplies raw daily OHLCV when the configured provider/account supports the symbol. Technical computations use only current/past data: log returns, SMA/EMA, Wilder-style RSI, MACD/signal, Bollinger bands, daily volatility, drawdown, relative volume and ATR when high/low/volume are aligned.

The current regime label is **asset-level**, based on moving-average structure and volatility. It is not a claim that the whole stock market is risk-on or risk-off. A benchmark universe, breadth data and sector mapping must exist before those labels can be produced responsibly.

Default forecasts are 1, 5 and 20 **observed trading sessions**. They show growth, sideways and decline probabilities together, plus confidence, analogue count, similarity, calibration status, snapshot timestamps and feature-based explanations. The same baseline method is independently replayed per horizon. No trade orders or strategy simulation are included.

Important current limits:

- Alpha Vantage daily prices are unadjusted in this adapter. Corporate actions can create artificial returns and anomalies.
- Compact history may be insufficient for independent long-horizon analogues.
- Exchange-date metadata is preserved, but complete exchange holiday calendars are not implemented.
- The quote currency is explicitly marked for verification. Similar tickers must not imply the same listing, exchange or currency.
- Historical data may be revised; it is not a point-in-time fundamental archive.
- No claim of a survivorship-free security universe is made.
- News, fundamentals, earnings surprises, market breadth, beta and sector-relative strength are absent when the relevant data is unavailable.

The synthetic financial names ORBT, CEDR and HIMA are fictional. Their curves are not AAPL, NVIDIA, Indian listed companies or real prices. Demo simulations evaluate code behavior, not investment performance.
