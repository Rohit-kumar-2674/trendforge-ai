import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

from trendforge.providers.base import (
    ProviderBatch,
    ProviderError,
    RateLimited,
    Transport,
    TrendProvider,
)
from trendforge.schemas import Domain, EntityInput, ObservationInput, utcnow


class AlphaVantageProvider(TrendProvider):
    name = "alpha_vantage"
    instructions = "Set ALPHA_VANTAGE_API_KEY and FINANCE_SYMBOLS. Daily unadjusted OHLCV; availability depends on plan and symbol."

    def __init__(
        self, api_key: str, symbols: list[str], transport: Transport | None = None
    ) -> None:
        super().__init__(transport or Transport(interval=13))
        self.api_key = api_key
        self.symbols = symbols[:10]

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.symbols)

    async def fetch(self) -> ProviderBatch:
        batch = ProviderBatch()
        for symbol in self.symbols:
            if not re.fullmatch(r"[A-Za-z0-9.^:_-]{1,30}", symbol):
                raise ProviderError("Invalid financial symbol")
            payload = await self.transport.json(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": self.api_key,
                },
            )
            if "Note" in payload or "Information" in payload:
                raise RateLimited(
                    "Alpha Vantage quota or plan restriction; check your plan and key"
                )
            if "Error Message" in payload:
                raise ProviderError("Alpha Vantage rejected the symbol or API request")
            series = payload.get("Time Series (Daily)")
            if not isinstance(series, dict) or not series:
                raise ProviderError("Alpha Vantage returned no daily history")
            timezone = payload.get("Meta Data", {}).get("5. Time Zone", "US/Eastern")
            try:
                zone = ZoneInfo(timezone)
            except (KeyError, ValueError) as exc:
                raise ProviderError("Unknown exchange timezone; refusing ambiguous dates") from exc
            entity = EntityInput(
                id=f"av:{symbol.upper()}",
                name=symbol.upper(),
                domain=Domain.STOCKS,
                category="Equity / provider symbol",
                region="UNSPECIFIED",
                keywords=[symbol.upper()],
                primary_metric="close",
                unit="quote currency (verify exchange)",
                cadence="trading_session",
            )
            batch.entities.append(entity)
            now = utcnow()
            for date, row in series.items():
                try:
                    # Source carries a trading DATE, not an exact tick time. 23:59 exchange time
                    # conservatively excludes incomplete/current trading days.
                    ts = datetime.combine(
                        datetime.strptime(date, "%Y-%m-%d").date(), time(23, 59), zone
                    )
                    if ts > now:
                        continue
                    values = {
                        metric: float(row[key])
                        for key, metric in [
                            ("1. open", "open"),
                            ("2. high", "high"),
                            ("3. low", "low"),
                            ("4. close", "close"),
                            ("5. volume", "volume"),
                        ]
                    }
                    if (
                        values["low"] > min(values["open"], values["close"])
                        or values["high"] < max(values["open"], values["close"])
                        or values["close"] <= 0
                    ):
                        raise ValueError("Invalid OHLC")
                    records = [
                        ObservationInput(
                            entity_id=entity.id,
                            provider=self.name,
                            metric=metric,
                            value=value,
                            source_timestamp=ts,
                            retrieved_at=now,
                            unit="shares" if metric == "volume" else entity.unit,
                            source_url="https://www.alphavantage.co/documentation/",
                            metadata={
                                "adjustment": "raw_unadjusted",
                                "source_date": date,
                                "exchange_timezone": timezone,
                                "timestamp_precision": "date",
                                "not_point_in_time_archive": True,
                            },
                        )
                        for metric, value in values.items()
                    ]
                    batch.observations.extend(records)
                except (ValueError, KeyError, TypeError):
                    batch.warnings.append("Skipped an invalid daily OHLCV row")
        return batch
