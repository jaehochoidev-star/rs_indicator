from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


class DataError(RuntimeError):
    """Incomplete or unavailable market data; never a successful empty screen."""


class NoTradingSession(RuntimeError):
    """Scheduled run has no new session; keep the previously published page."""


@dataclass
class MarketData:
    as_of: date
    sessions: pd.DatetimeIndex
    universe: pd.DataFrame  # index=ticker; columns=name, market
    closes: pd.DataFrame  # session x ticker, adjusted to as_of
    turnover: pd.DataFrame  # session x ticker, actual KRW (not close * volume)


class MarketDataProvider(Protocol):
    def collect(self, requested: date) -> MarketData: ...
