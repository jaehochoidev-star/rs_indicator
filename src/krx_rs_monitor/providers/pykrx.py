from contextlib import contextmanager, redirect_stdout
from datetime import date, timedelta
from importlib.metadata import version
from pathlib import Path
import io
import time
from unittest.mock import patch

import pandas as pd
import requests

from ..models import DataError, MarketData, NoTradingSession


@contextmanager
def request_timeout(seconds: float):
    """pykrx has no public timeout option; scope the default to this CLI run."""
    original = requests.sessions.Session.request

    def bounded(session, *args, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return original(session, *args, **kwargs)

    with patch.object(requests.sessions.Session, "request", bounded):
        yield


class PykrxProvider:
    """Serial, throttled collection; adjusted prices and actual daily KRW value.

    Cache keys include pykrx version and valuation date. Adjusted price history
    must not be reused across valuation dates because corporate actions change it.
    """

    def __init__(self, cache_dir=Path("data/cache"), *, delay=1.0, timeout=20.0,
                 refresh=False, progress=print, stock_api=None, skip_nontrading=False):
        if delay < 1 or timeout <= 0:
            raise ValueError("delay must be >= 1 second and timeout positive.")
        self.cache_dir = Path(cache_dir) / ("v1-pykrx-" + version("pykrx"))
        self.delay, self.timeout, self.refresh = delay, timeout, refresh
        self.progress = progress
        self.stock = stock_api
        self.skip_nontrading = skip_nontrading

    def _frame(self, key, call, required):
        path = self.cache_dir / (key + ".json")
        if path.exists() and not self.refresh:
            try:
                frame = pd.read_json(path, orient="table")
                self._validate(frame, required)
                return frame
            except (ValueError, KeyError, DataError):
                self.progress(f"Invalid cache, refetching: {key}")
        for attempt in range(3):
            try:
                time.sleep(self.delay)
                frame = call()
                self._validate(frame, required)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                frame.to_json(temporary, orient="table", force_ascii=False)
                temporary.replace(path)
                return frame
            except (requests.RequestException, ValueError, KeyError, TypeError, DataError) as exc:
                # Do not print upstream errors: login responses may contain secrets.
                if attempt == 2:
                    raise DataError(
                        f"pykrx query failed: {key} ({type(exc).__name__}). "
                        "Check network, KRX_ID/KRX_PW, and provider availability. "
                        "No ranking has been published."
                    ) from None
                self.progress(f"Retry {attempt + 1}/2: {key}")
                time.sleep(2 ** attempt)

    @staticmethod
    def _validate(frame, required):
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise DataError("Empty provider response.")
        if not set(required).issubset(frame.columns) or frame.index.has_duplicates:
            raise DataError("Unexpected provider schema.")

    def collect(self, requested: date) -> MarketData:
        with request_timeout(self.timeout):
            if self.stock is None:
                # pykrx logs the login ID while importing. Keep it out of logs.
                with redirect_stdout(io.StringIO()):
                    from pykrx import stock
                self.stock = stock
            return self._collect(requested)

    def _collect(self, requested):
        start = requested - timedelta(days=180)
        end_key, start_key = requested.strftime("%Y%m%d"), start.strftime("%Y%m%d")
        self.progress(f"Collecting trading calendar through {requested} ...")
        calendar = self._frame(
            f"{end_key}/calendar-{start_key}",
            lambda: self.stock.get_index_ohlcv_by_date(start_key, end_key, "1001"),
            ["종가"],
        )
        sessions = pd.DatetimeIndex(calendar.index).normalize().sort_values()
        sessions = sessions[(sessions.date <= requested) & (sessions.date >= start)]
        if len(sessions) < 61:
            raise DataError("Provider returned fewer than 61 market sessions.")
        sessions = sessions[-61:]
        as_of = sessions[-1].date()
        if (requested - as_of).days > 10:
            raise DataError("Provider calendar is stale by more than 10 days.")
        if self.skip_nontrading and as_of != requested:
            raise NoTradingSession(f"No new session for {requested}; latest is {as_of}. Keeping published results.")
        anchor = as_of.strftime("%Y%m%d")
        first = sessions[0].strftime("%Y%m%d")
        self.progress(f"Effective session: {as_of}; loading KOSPI + KOSDAQ universe ...")
        parts = []
        for market in ("KOSPI", "KOSDAQ"):
            frame = self._frame(
                f"{anchor}/universe-{market}",
                lambda m=market: self.stock.get_market_price_change_by_ticker(anchor, anchor, market=m),
                ["종목명", "종가"],
            )
            # Price-change endpoint can include delisted tickers with close=0.
            frame = frame.loc[frame["종가"] > 0]
            if frame.empty:
                raise DataError(f"No listed tickers returned for {market}.")
            frame = frame[["종목명"]].rename(columns={"종목명": "name"})
            frame.index = frame.index.astype(str).str.zfill(6)
            frame["market"] = market
            parts.append(frame)
        universe = pd.concat(parts)
        if universe.index.has_duplicates:
            raise DataError("Duplicated tickers in KOSPI/KOSDAQ universe.")

        values = []
        for session in sessions[-20:]:
            day = session.strftime("%Y%m%d")
            daily = []
            for market in ("KOSPI", "KOSDAQ"):
                frame = self._frame(
                    f"{anchor}/turnover-{day}-{market}",
                    lambda d=day, m=market: self.stock.get_market_ohlcv_by_ticker(d, market=m),
                    ["거래대금"],
                )
                frame.index = frame.index.astype(str).str.zfill(6)
                daily.append(frame["거래대금"])
            combined = pd.concat(daily)
            if combined.index.has_duplicates:
                raise DataError(f"Duplicate turnover tickers on {day}.")
            values.append(combined.rename(session))
            self.progress(f"Daily turnover: {day}")
        turnover = pd.DataFrame(values).reindex(columns=universe.index)

        histories = {}
        for number, ticker in enumerate(universe.index, 1):
            frame = self._frame(
                f"{anchor}/adjusted-{first}-{ticker}",
                lambda t=ticker: self.stock.get_market_ohlcv_by_date(first, anchor, t, adjusted=True),
                ["종가"],
            )
            frame.index = pd.DatetimeIndex(frame.index).normalize()
            histories[ticker] = frame["종가"].reindex(sessions)
            if number == 1 or number % 50 == 0 or number == len(universe):
                self.progress(f"Adjusted histories: {number}/{len(universe)}")
        return MarketData(as_of, sessions, universe, pd.DataFrame(histories), turnover)
