import json
from pathlib import Path
import textwrap
import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/monitor.yml'

def script(name, next_name):
    text = WORKFLOW.read_text(encoding='utf-8')
    block = text.split('      - name: '+name)[1].split(next_name)[0]
    return textwrap.dedent(block.split("python - <<'PY'\n")[1].rsplit('          PY', 1)[0])

@pytest.mark.parametrize('published,status,scheduled,expected', [
    ('2026-11-13','success',True,False),
    ('2026-11-12','success',True,True),
    ('2026-11-16','success',True,False),
    ('2026-11-13','failed',True,True),
    ('2026-11-13','success',False,True),
])
def test_backup_only_collects_unpublished_session(tmp_path, monkeypatch, published, status, scheduled, expected):
    code=script('Select cache date','      - uses: actions/cache/restore')
    monkeypatch.chdir(tmp_path)
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/latest.json').write_text(json.dumps({'status':status,'as_of':published}))
    out=tmp_path/'output'; summary=tmp_path/'summary'
    for name,value in {'REQUESTED_DATE':'2026-11-13','CACHE_DATE':'','SCHEDULED':str(scheduled).lower(),'GITHUB_OUTPUT':str(out),'GITHUB_STEP_SUMMARY':str(summary)}.items():
        monkeypatch.setenv(name,value)
    exec(code,{})
    assert ('collect='+str(expected).lower()) in out.read_text()

@pytest.mark.parametrize('instant,expected', [('2026-11-13T14:59:00+00:00',True),('2026-11-13T15:00:00+00:00',False),('2026-11-15T14:59:00+00:00',False),('2026-11-15T15:00:00+00:00',True)])
def test_korean_weekend_boundary(tmp_path, monkeypatch, instant, expected):
    code=script('Check Korean weekday before collection','      - name: Select cache date')
    code=code.replace("datetime.now(ZoneInfo('Asia/Seoul'))",f"datetime.fromisoformat('{instant}').astimezone(ZoneInfo('Asia/Seoul'))")
    out=tmp_path/'output'; monkeypatch.setenv('GITHUB_OUTPUT',str(out)); monkeypatch.setenv('GITHUB_STEP_SUMMARY',str(tmp_path/'summary'))
    exec(code,{})
    assert out.read_text().strip()=='collect='+str(expected).lower()
