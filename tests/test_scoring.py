from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from krx_rs_monitor.cli import main, resolve_date, run
from krx_rs_monitor.models import DataError, MarketData
from krx_rs_monitor.scoring import ScreenConfig, score


@pytest.fixture
def market():
    dates = pd.bdate_range("2026-01-01", periods=61)
    tickers = [f"{i:06d}" for i in range(1, 101)]
    universe = pd.DataFrame({"name": [f"TEST-{i}" for i in range(100)],
                             "market": ["KOSPI"] * 50 + ["KOSDAQ"] * 50}, index=tickers)
    closes = pd.DataFrame({t: 100 * (1 + i / 10000) ** np.arange(61)
                           for i, t in enumerate(tickers, 1)}, index=dates)
    turnover = pd.DataFrame(10_000_000_000.0, index=dates[-20:], columns=tickers)
    return MarketData(dates[-1].date(), dates, universe, closes, turnover)


def test_combined_percentiles_and_exact_returns(market):
    ranked, top, stats = score(market, ScreenConfig())
    strongest = ranked.iloc[0]
    assert strongest.ticker == "000100"
    assert strongest.RS_Score == 100
    assert strongest.return60 == pytest.approx((1.01 ** 60 - 1) * 100)
    assert strongest.return1 == pytest.approx(1)
    assert ranked.set_index("ticker").loc["000050", "RS20"] == 50
    assert len(top) == 11  # inclusive RS >= 90
    assert stats["matched"] == 11


def test_filter_after_ranking_and_inclusive_turnover(market):
    market.turnover["000100"] = 0
    market.turnover["000099"] = 5_000_000_000
    market.turnover.loc[market.sessions[-20], "000099"] = 0
    market.turnover.loc[market.sessions[-1], "000099"] = 10_000_000_000
    ranked, top, _ = score(market, ScreenConfig())
    row = ranked.set_index("ticker").loc["000099"]
    assert row.RS20 == 99
    assert row.turnover_20d_avg == pytest.approx(5_000_000_000)
    assert "000099" in top.ticker.values
    assert "000100" not in top.ticker.values
    market.turnover.loc[market.sessions[-1], "000099"] -= 1
    assert "000099" not in score(market, ScreenConfig())[1].ticker.values


def test_average_rank_for_ties(market):
    market.closes["000099"] = market.closes["000100"]
    ranked, _, _ = score(market, ScreenConfig())
    assert ranked.iloc[0].RS20 == 99.5
    assert ranked.iloc[1].RS20 == 99.5
    assert ranked.iloc[0].ticker == "000099"


def test_weight_order_and_normalization(market):
    market.closes.loc[market.sessions[-2], "000100"] *= 2
    ranked, _, _ = score(market, ScreenConfig())
    row = ranked.set_index("ticker").loc["000100"]
    assert row.RS_Score == pytest.approx(row.RS1 * .1 + row.RS5 * .3 + row.RS20 * .4 + row.RS60 * .2)
    single, _, _ = score(market, ScreenConfig(weights=(0, 0, 1, 0)))
    assert (single.RS_Score == single.RS20).all()


def test_short_history_not_filled(market):
    market.closes.loc[market.sessions[0], "000100"] = np.nan
    _, top, stats = score(market, ScreenConfig())
    assert stats["eligible"] == 99
    assert stats["excluded_short_or_invalid_history"] == 1
    assert "000100" not in top.ticker.values
    assert top.iloc[0].RS20 == 100


def test_partial_turnover_fails(market):
    market.turnover.iloc[0, 0] = np.nan
    with pytest.raises(DataError, match="turnover"):
        score(market, ScreenConfig())


def test_missing_provider_ticker_fails(market):
    market.closes = market.closes.drop(columns="000001")
    with pytest.raises(DataError, match="omitted"):
        score(market, ScreenConfig())


def test_top20_and_empty_are_valid(market):
    _, top, stats = score(market, ScreenConfig(rs20_min=0, rs5_min=0))
    assert len(top) == 40 and stats["matched"] == 100
    _, top, stats = score(market, ScreenConfig(turnover_min=1e20))
    assert top.empty and stats["matched"] == 0


@pytest.mark.parametrize("weights", [(0, 0, 0, 0), (-1, 1, 1, 1), (float("nan"), 1, 1, 1), (1, 2)])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        ScreenConfig(weights=weights)


def test_date_cutoff():
    now = datetime(2026, 10, 6, 17, 59, tzinfo=ZoneInfo("Asia/Seoul"))
    assert resolve_date(None, now).isoformat() == "2026-10-05"
    with pytest.raises(ValueError):
        resolve_date("2026-10-06", now)
    assert resolve_date(None, now.replace(hour=18)).isoformat() == "2026-10-06"


def test_pipeline_exports_and_records_effective_date(market, tmp_path, capsys):
    class FixtureProvider:
        def collect(self, requested):
            return market
    result = run(FixtureProvider(), market.as_of, ScreenConfig(), tmp_path)
    assert result["statistics"]["displayed"] == 11
    output = pd.read_csv(tmp_path / f"top40-{market.as_of}.csv", dtype={"ticker": str})
    assert output.iloc[0].ticker == "000100"
    assert "TEST-99" in capsys.readouterr().out


def test_failure_does_not_publish(tmp_path):
    class FailedProvider:
        def collect(self, requested):
            raise DataError("Unavailable")
    with pytest.raises(DataError):
        run(FailedProvider(), datetime(2026, 1, 1).date(), ScreenConfig(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_missing_credentials_are_actionable(monkeypatch, capsys):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    assert main(["--date", "2026-01-01"]) == 2
    assert "--login" in capsys.readouterr().err
