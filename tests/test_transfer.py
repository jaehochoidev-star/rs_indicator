import pandas as pd
import pytest
from krx_rs_monitor.models import DataError
from krx_rs_monitor.providers.pykrx import PykrxProvider


@pytest.mark.parametrize('scenario', ['transfer', 'missing', 'ipo', 'negative'])
def test_historical_market_transfer(tmp_path, monkeypatch, scenario):
    monkeypatch.setattr('krx_rs_monitor.providers.pykrx.time.sleep', lambda _: None)
    sessions = pd.bdate_range(end='2026-10-20', periods=61)
    fetched = []

    class Stock:
        def get_index_ohlcv_by_date(self, *args):
            return pd.DataFrame({'종가': 100}, index=sessions)

        def get_market_price_change_by_ticker(self, start, end, market):
            ticker = '000001' if market == 'KOSPI' else '250030'
            return pd.DataFrame({'종목명': ['fixture'], '종가': [100]}, index=[ticker])

        def get_market_sector_classifications(self, day, market):
            return pd.DataFrame({'업종명': ['fixture']}, index=['000001'])

        def get_market_ohlcv_by_ticker(self, day, market):
            old = day < sessions[-4].strftime('%Y%m%d')
            if market == 'KONEX':
                ticker = '250030' if scenario == 'transfer' else '999999'
                return pd.DataFrame({'거래대금': [0]}, index=[ticker])
            ticker = '000001' if market == 'KOSPI' else '250030'
            if market == 'KOSDAQ' and old and scenario != 'negative':
                ticker = '888888'
            value = -1 if scenario == 'negative' and market == 'KOSDAQ' and old else 12e9
            return pd.DataFrame({'거래대금': [value]}, index=[ticker])

        def get_market_ohlcv_by_date(self, start, end, ticker, adjusted):
            fetched.append(ticker)
            dates = sessions[-4:] if scenario == 'ipo' and ticker == '250030' else sessions
            return pd.DataFrame({'종가': 100}, index=dates)

    provider = PykrxProvider(tmp_path, stock_api=Stock(), progress=lambda _: None)
    if scenario in ('missing', 'negative'):
        with pytest.raises(DataError, match='turnover data: 250030'):
            provider.collect(sessions[-1].date())
        assert fetched == ['250030']
    else:
        data = provider.collect(sessions[-1].date())
        assert set(data.universe.index) == {'000001', '250030'}
        if scenario == 'transfer':
            assert (data.turnover['250030'].iloc[:16] == 0).all()
            assert (data.turnover['250030'].iloc[16:] == 12e9).all()
        else:
            assert data.closes['250030'].isna().sum() == 57
