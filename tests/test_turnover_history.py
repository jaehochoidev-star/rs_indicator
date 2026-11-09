import json
import numpy as np
import pandas as pd
import pytest
from krx_rs_monitor.turnover import leaders, write_leaders
from krx_rs_monitor.models import DataError
from krx_rs_monitor.dashboard import render
from test_dashboard import fixture_run


def history_fixture():
    sessions = pd.to_datetime(['2026-09-24','2026-09-25','2026-09-28','2026-09-29','2026-10-02'])
    universe = pd.DataFrame({'name': ['steady', 'new', 'resumed'], 'market': ['KOSPI'] * 3}, index=['000001','000002','000003'])
    history = pd.DataFrame({'000001': [1e8, 2e8, 3e8, 4e8, 6e8],
                            '000002': [np.nan, np.nan, np.nan, np.nan, 9e8],
                            '000003': [0, 0, 0, 0, 7e8]}, index=sessions)
    return universe, history


def test_history_aligned_by_ticker_and_actual_sessions():
    universe, history = history_fixture()
    frame = leaders(universe, history.iloc[-1], history=history).set_index('ticker')
    assert list(frame.index) == ['000002','000003','000001']
    assert frame.loc['000001','turnover_change_pct'] == 50
    assert pd.isna(frame.loc['000002','turnover_2026-09-29'])
    assert pd.isna(frame.loc['000003','turnover_change_pct'])
    assert frame.loc['000003','turnover_2026-09-29'] == 0
    assert 'turnover_2026-09-26' not in frame


def test_history_latest_must_match_ranking():
    universe, history = history_fixture()
    with pytest.raises(DataError, match='end with'):
        leaders(universe, history.iloc[-1] * 2, history=history)


def test_history_display_dates_change_and_missing(tmp_path):
    source, target = tmp_path/'output', tmp_path/'docs'
    fixture_run(source)
    universe, history = history_fixture()
    frame = leaders(universe, history.iloc[-1], history=history)
    write_leaders(frame, source, '2026-10-02')
    path = source/'run-2026-10-02.json'
    meta = json.loads(path.read_text())
    meta.update(turnover_displayed=3, turnover_sessions=[d.date().isoformat() for d in history.index])
    path.write_text(json.dumps(meta))
    render(source, target)
    html = (target/'index.html').read_text(encoding='utf-8')
    assert '09/24' in html and '10/02 · 기준일' in html
    assert '+50.0%' in html and '>—</td>' in html
    assert '전일 대비' in html
    assert '>0.0</td>' in html
    copied = pd.read_csv(target/'turnover40-2026-10-02.csv')
    assert 'turnover_2026-09-29' in copied
