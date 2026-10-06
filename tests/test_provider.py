import pandas as pd
import pytest

from krx_rs_monitor.models import DataError
from krx_rs_monitor.providers.pykrx import PykrxProvider, request_timeout


def test_cache_preserves_ticker_and_prevents_repeat_request(tmp_path, monkeypatch):
    monkeypatch.setattr("krx_rs_monitor.providers.pykrx.time.sleep", lambda _: None)
    provider = PykrxProvider(tmp_path)
    original = pd.DataFrame({"종가": [123.0]}, index=pd.Index(["005930"], name="티커"))
    calls = []

    def fetch():
        calls.append(1)
        return original

    provider._frame("sample", fetch, ["종가"])
    restored = provider._frame("sample", fetch, ["종가"])
    pd.testing.assert_frame_equal(restored, original)
    assert len(calls) == 1


def test_empty_response_retries_and_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr("krx_rs_monitor.providers.pykrx.time.sleep", lambda _: None)
    provider = PykrxProvider(tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return pd.DataFrame()

    with pytest.raises(DataError, match="No ranking"):
        provider._frame("empty", fetch, ["종가"])
    assert len(calls) == 3
    assert not list(tmp_path.rglob("*.json"))


def test_provider_end_to_end_and_weekend_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr("krx_rs_monitor.providers.pykrx.time.sleep", lambda _: None)
    sessions = pd.bdate_range(end="2026-03-27", periods=61)
    calls = []

    class FakeStock:
        def get_index_ohlcv_by_date(self, start, end, ticker):
            calls.append("calendar")
            return pd.DataFrame({"종가": [2500] * 61}, index=sessions)

        def get_market_price_change_by_ticker(self, start, end, market):
            calls.append(market)
            ticker = "005930" if market == "KOSPI" else "035900"
            return pd.DataFrame({"종목명": ["FIXTURE"], "종가": [100]}, index=[ticker])

        def get_market_ohlcv_by_ticker(self, day, market):
            ticker = "005930" if market == "KOSPI" else "035900"
            return pd.DataFrame({"거래대금": [12_000_000_000]}, index=[ticker])

        def get_market_ohlcv_by_date(self, start, end, ticker, adjusted):
            assert adjusted is True
            return pd.DataFrame({"종가": range(100, 161)}, index=sessions)

    requested = pd.Timestamp("2026-03-29").date()
    provider = PykrxProvider(tmp_path, stock_api=FakeStock(), progress=lambda _: None)
    result = provider.collect(requested)
    assert result.as_of.isoformat() == "2026-03-27"
    assert result.closes.shape == (61, 2)
    assert result.turnover.shape == (20, 2)
    assert result.turnover.loc[sessions[-1], "005930"] == 12_000_000_000
    again = provider.collect(requested)
    assert calls == ["calendar", "KOSPI", "KOSDAQ"]
    pd.testing.assert_frame_equal(result.closes, again.closes)


def test_timeout_is_scoped(monkeypatch):
    import requests
    observed = []

    def original(self, *args, **kwargs):
        observed.append(kwargs["timeout"])

    monkeypatch.setattr(requests.sessions.Session, "request", original)
    with request_timeout(12):
        requests.Session().request("GET", "https://example.invalid")
    assert observed == [12]
    assert requests.sessions.Session.request is original


def test_scheduled_holiday_skips_before_stock_collection(tmp_path, monkeypatch):
    from krx_rs_monitor.models import NoTradingSession
    monkeypatch.setattr("krx_rs_monitor.providers.pykrx.time.sleep", lambda _: None)
    class CalendarOnly:
        def get_index_ohlcv_by_date(self, *args):
            return pd.DataFrame({"종가": [2500] * 61}, index=pd.bdate_range(end="2026-03-27", periods=61))
    provider = PykrxProvider(tmp_path, stock_api=CalendarOnly(), skip_nontrading=True)
    with pytest.raises(NoTradingSession):
        provider.collect(pd.Timestamp("2026-03-29").date())
