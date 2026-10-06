import csv
import json
from datetime import date

from krx_rs_monitor.sectors import enrich
from krx_rs_monitor.dashboard import render
from test_dashboard import fixture_run


def test_enrichment_preserves_rankings_and_shows_sector(tmp_path):
    source, enriched, site = (tmp_path / name for name in ('source', 'enriched', 'site'))
    fixture_run(source)
    (source / 'run-2026-10-02.json').rename(source / 'latest.json')
    class SectorProvider:
        def get_sectors(self, as_of):
            assert as_of == date(2026, 10, 2)
            return {'005930': '전기전자 <부품>'}
    enrich(source, enriched, SectorProvider())
    for prefix in ('ranked','top20'):
        def rows(path):
            with path.open(encoding='utf-8-sig', newline='') as f:
                return list(csv.DictReader(f))
        old = rows(source / f'{prefix}-2026-10-02.csv')
        new = rows(enriched / f'{prefix}-2026-10-02.csv')
        assert new[0].pop('sector') == '전기전자 <부품>'
        assert new == old
    meta = json.loads((enriched / 'run-2026-10-02.json').read_text(encoding='utf-8'))
    assert meta['generated_at'] == '2026-10-06T23:00:00+09:00'
    render(enriched, site)
    html = (site / 'index.html').read_text(encoding='utf-8')
    assert '<span class="sector">전기전자 &lt;부품&gt;</span>' in html
    assert html.index('전기전자 &lt;부품&gt;') < html.index('&lt;script&gt;alert(1)')
