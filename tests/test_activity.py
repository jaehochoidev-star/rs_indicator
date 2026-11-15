import json
import numpy as np
import pandas as pd
import pytest
from krx_rs_monitor.activity import upper_price, select_activity, build
from krx_rs_monitor.models import DataError
from krx_rs_monitor.dashboard import render
from test_dashboard import fixture_run


def snapshot():
    return pd.DataFrame({
        'name': ['<limit>', 'near', 'new', 'large'], 'sector': ['반도체'] * 4,
        'market': ['KOSPI','KOSDAQ','KOSDAQ','KOSPI'],
        'close': [2595,2590,2595,10000], 'base_price': [1999,1999,1999,10000],
        'volume': [9_999_999,10_000_000,10_000_001,25_000_000],
        'turnover_today': [1e10,2e10,3e10,4e10], 'change_pct': [29.81,29.56,29.81,0],
        'is_new_listing': [False,False,True,False],
    }, index=['000001','000002','000003','000004'])


@pytest.mark.parametrize('base,expected', [(1000,1300),(1999,2595),(4995,6490),(19990,25950),(77000,100100),(0,0)])
def test_upper_limit_tick_truncation(base, expected):
    assert upper_price(base) == expected


def test_screens_are_independent_inclusive_and_not_capped():
    limits, volume = select_activity(snapshot())
    assert limits.ticker.tolist() == ['000001']
    assert volume.ticker.tolist() == ['000004','000003','000002']
    many = pd.concat([snapshot().iloc[[3]]] * 45, ignore_index=True)
    many.index = [f'{i:06}' for i in range(45)]
    assert len(select_activity(many)[1]) == 45


def test_bad_snapshot_fails():
    data = snapshot()
    data.loc['000001','volume'] = np.nan
    with pytest.raises(DataError):
        select_activity(data)


def test_build_and_render_activity(tmp_path, monkeypatch):
    source, target = tmp_path/'out', tmp_path/'docs'
    fixture_run(source)
    monkeypatch.setattr('krx_rs_monitor.activity.collect_activity', lambda *args: snapshot())
    build(source, provider=object())
    render(source, target)
    html = (target/'index.html').read_text(encoding='utf-8')
    assert '&lt;limit&gt;' in html and '<limit>' not in html
    assert '상한가 마감 종목' in html and '거래량 1,000만 주 이상' in html
    assert '10,000,000' in html
    assert (target/'volume10m-2026-10-02.csv').exists()
    assert (target/'limit-up-2026-10-02.csv').exists()
    meta = json.loads((target/'latest.json').read_text(encoding='utf-8'))
    assert meta['activity']['limit_up'] == 1
    assert meta['activity']['volume10m'] == 3


def test_empty_list_is_success_and_partial_list_preserves_page(tmp_path, monkeypatch):
    source, target = tmp_path/'out', tmp_path/'docs'
    fixture_run(source)
    data = snapshot()
    data['volume'] = 0
    monkeypatch.setattr('krx_rs_monitor.activity.collect_activity', lambda *args: data)
    build(source, provider=object())
    render(source, target)
    original = (target/'index.html').read_bytes()
    assert '해당 기준일에 조건을 충족한 종목이 없습니다.' in original.decode('utf-8')
    (source/'volume10m-2026-10-02.csv').unlink()
    with pytest.raises(FileNotFoundError):
        render(source, target)
    assert (target/'index.html').read_bytes() == original
