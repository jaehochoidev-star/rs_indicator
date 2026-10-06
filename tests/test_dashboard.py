import json
import pandas as pd
import pytest

from krx_rs_monitor.dashboard import render


def fixture_run(folder, *, rows=1):
    folder.mkdir()
    meta = {"status": "success", "as_of": "2026-10-02", "generated_at": "2026-10-06T23:00:00+09:00",
            "settings": {"weights": [10,30,40,20], "avg_turnover_min": 5e9, "turnover_min": 1e10,
                         "rs20_min": 90, "rs5_min": 90, "top": 20},
            "statistics": {"universe": 2766, "eligible": 2700, "matched": rows, "displayed": rows}}
    (folder / "run-2026-10-02.json").write_text(json.dumps(meta), encoding="utf-8")
    data = [{"ticker":"005930", "name":"<script>alert(1)</script>", "market":"KOSPI",
             "RS_Score":95, "RS1":90, "RS5":95, "RS20":97, "RS60":93,
             "turnover_20d_avg":5e9, "turnover_today":1e10, "passes":True}]
    frame = pd.DataFrame(data).iloc[:rows]
    for name in ("top20", "ranked"):
        frame.to_csv(folder / f"{name}-2026-10-02.csv", index=False, encoding="utf-8-sig")


def test_html_escapes_names_and_copies_only_public_outputs(tmp_path):
    source, target = tmp_path / "output", tmp_path / "docs"
    fixture_run(source)
    (source / "secret.txt").write_text("do not publish")
    render(source, target)
    html = (target / "index.html").read_text(encoding="utf-8")
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '<script>alert(1)</script>' not in html
    assert '2026-10-02' in html and '2,766' in html
    assert not (target / "secret.txt").exists()
    assert (target / "top20-2026-10-02.csv").exists()


def test_empty_screen_is_distinct_from_pending(tmp_path):
    source, target = tmp_path / "output", tmp_path / "docs"
    render(source, target, allow_empty=True)
    assert '첫 시장 데이터를 수집' in (target / "index.html").read_text(encoding="utf-8")
    fixture_run(source, rows=0)
    render(source, target)
    assert '조건을 모두 충족한 종목이 없습니다' in (target / "index.html").read_text(encoding="utf-8")


def test_partial_run_preserves_existing_page(tmp_path):
    source, target = tmp_path / "output", tmp_path / "docs"
    fixture_run(source)
    render(source, target)
    original = (target / "index.html").read_bytes()
    (source / "top20-2026-10-02.csv").write_text("ticker\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row count"):
        render(source, target)
    assert (target / "index.html").read_bytes() == original
