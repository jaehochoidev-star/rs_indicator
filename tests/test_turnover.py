import json
import numpy as np
import pandas as pd
import pytest

from krx_rs_monitor.models import DataError
from krx_rs_monitor.turnover import leaders, write_leaders
from krx_rs_monitor.dashboard import render
from test_dashboard import fixture_run


def test_top40_includes_new_stocks_and_breaks_ties_by_ticker():
    universe = pd.DataFrame({'name': ['new stock'] * 45, 'market': ['KOSDAQ'] * 45},
                            index=[f'{i:06}' for i in range(45)])
    daily = pd.Series([100] * 44 + [200], index=universe.index)
    result = leaders(universe, daily)
    assert len(result) == 40
    assert result.ticker.iloc[0] == '000044'
    assert result.ticker.iloc[1] == '000000'
    assert result.ticker.iloc[-1] == '000038'


@pytest.mark.parametrize('value', [np.nan, np.inf, -1])
def test_invalid_daily_turnover_is_not_published(value):
    universe = pd.DataFrame({'name': ['stock']}, index=['000001'])
    with pytest.raises(DataError):
        leaders(universe, pd.Series([value], index=universe.index))


def test_dashboard_turnover_separate_from_rs_and_escaped(tmp_path):
    source, destination = tmp_path / 'output', tmp_path / 'docs'
    fixture_run(source)
    path = source / 'run-2026-10-02.json'
    meta = json.loads(path.read_text())
    meta['turnover_displayed'] = 1
    path.write_text(json.dumps(meta))
    frame = pd.DataFrame([{'ticker':'000001', 'name':'<new>', 'sector':'<sector>',
                           'market':'KOSDAQ', 'turnover_today': 123e8}])
    write_leaders(frame, source, '2026-10-02')
    render(source, destination)
    html = (destination / 'index.html').read_text(encoding='utf-8')
    assert '당일 거래대금 TOP 40' in html
    assert '&lt;new&gt;' in html and '&lt;sector&gt;' in html
    assert '123.0' in html
    assert "querySelectorAll('#ranked-rows tr[data-market]')" in html
    assert (destination / 'turnover40-2026-10-02.csv').exists()
    original = (destination / 'index.html').read_bytes()
    frame['turnover_today'] = -1
    write_leaders(frame, source, '2026-10-02')
    with pytest.raises(ValueError, match='Invalid turnover'):
        render(source, destination)
    assert (destination / 'index.html').read_bytes() == original
