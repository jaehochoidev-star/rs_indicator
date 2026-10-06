"""Generate a standalone static dashboard from a completed, validated run."""
import argparse
import csv
from datetime import datetime
from html import escape
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

REPO = "https://github.com/jaehochoidev-star/rs_indicator"


def render(source: Path, destination: Path, *, allow_empty=False):
    runs = sorted(source.glob("run-????-??-??.json"))
    if not runs and not allow_empty:
        raise ValueError("No completed run metadata found; preserving the existing dashboard.")
    meta = json.loads(runs[-1].read_text(encoding="utf-8")) if runs else None
    rows = []
    if meta:
        if meta.get("status") != "success":
            raise ValueError("Only a successful run can be published.")
        stamp = meta["as_of"]
        datetime.strptime(stamp, "%Y-%m-%d")
        top_file = source / f"top20-{stamp}.csv"
        with top_file.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != meta["statistics"]["displayed"]:
            raise ValueError("CSV row count does not match run metadata.")
        if any(row.get("passes") != "True" for row in rows):
            raise ValueError("TOP20 contains a row that failed the screen.")
        # Read and validate all source data before changing the publication folder.
        if not (source / f"ranked-{stamp}.csv").is_file():
            raise ValueError("Full ranking CSV is missing.")
    settings = meta["settings"] if meta else {
        "weights": [10, 30, 40, 20], "avg_turnover_min": 5e9,
        "turnover_min": 1e10, "rs20_min": 90, "rs5_min": 90, "top": 20,
    }
    stats = meta["statistics"] if meta else {}
    def e(value): return escape(str(value), quote=True)
    as_of = meta["as_of"] if meta else "첫 수집 대기"
    generated = (datetime.fromisoformat(meta["generated_at"]).astimezone(ZoneInfo("Asia/Seoul"))
                 .strftime("%Y-%m-%d %H:%M KST")) if meta else "첫 수집이 끝나면 자동으로 표시됩니다"
    body = []
    for number, row in enumerate(rows, 1):
        score = float(row["RS_Score"])
        if not 0 <= score <= 100:
            raise ValueError("Invalid RS Score")
        cells = "".join(f'<td class="num">{float(row[key]):.1f}</td>' for key in ("RS1", "RS5", "RS20", "RS60"))
        body.append(f'''<tr data-market="{e(row['market'])}"><td class="rank">{number:02}</td>
<td><b>{e(row['name'])}</b><span class="ticker">{e(row['ticker'])}</span></td>
<td><span class="market">{e(row['market'])}</span></td>
<td class="score"><strong>{score:.1f}</strong><span class="bar"><i style="width:{score:.1f}%"></i></span></td>
{cells}<td class="num">{float(row['turnover_20d_avg'])/1e8:,.1f}</td><td class="num">{float(row['turnover_today'])/1e8:,.1f}</td></tr>''')
    empty = "조건을 모두 충족한 종목이 없습니다." if meta else "첫 시장 데이터를 수집하고 있습니다. 완료되면 순위가 표시됩니다."
    table = "".join(body) or f'<tr><td colspan="10" class="empty">{empty}</td></tr>'
    downloads = '<span class="muted">CSV는 첫 수집 후 제공됩니다</span>'
    if meta:
        downloads = f'<a class="button" href="top20-{as_of}.csv" download>TOP {settings["top"]} CSV ↓</a><a href="ranked-{as_of}.csv" download>전체 순위 CSV ↓</a>'
    weights = settings['weights']
    total = sum(weights)
    formula = " + ".join(f"RS{n} × {w/total:.0%}" for n, w in zip((1,5,20,60), weights))
    html = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="KOSPI와 KOSDAQ의 상대강도 순위와 거래대금 조건을 매 거래일 확인합니다.">
<title>KRX RS Monitor · 상대강도 TOP {settings['top']}</title>
<style>
:root{{--ink:#152c37;--muted:#647780;--line:#dce5e6;--green:#08785f;--bg:#f5f7f4}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Malgun Gothic",sans-serif}}a{{color:var(--green);text-decoration:none}}a:hover{{text-decoration:underline}}header{{background:#102e39;color:white;padding:24px max(24px,calc((100vw - 1220px)/2))}}.brand{{font-size:14px;letter-spacing:.15em;font-weight:750}}.brand span{{color:#72d6b7}}header p{{margin:4px 0 0;color:#bfd0d6;font-size:12px}}main{{max-width:1270px;margin:auto;padding:44px 24px 36px}}.eyebrow{{color:var(--green);font-weight:700;font-size:12px;letter-spacing:.12em}}h1{{font-size:clamp(30px,4vw,46px);line-height:1.2;letter-spacing:-.04em;margin:10px 0 16px}}.lede{{color:var(--muted);margin:0}}.hero{{display:flex;gap:20px;justify-content:space-between;align-items:center;margin-bottom:30px}}.date-box{{text-align:right;min-width:230px;font-size:12px;color:var(--muted)}}.date-box strong{{display:block;color:var(--ink);font-size:23px}}.pill{{display:inline-block;border:1px solid #b9d9cc;color:var(--green);background:#e9f5ef;border-radius:20px;padding:4px 11px;margin-bottom:8px;font-size:11px;font-weight:650}}.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}}.stat{{padding:20px 24px;border:1px solid var(--line);border-radius:12px;background:white}}.stat span{{color:var(--muted);font-size:12px}}.stat b{{display:block;font-size:28px;line-height:1.5}}.stat small{{font-size:11px;color:var(--muted)}}.panel{{background:white;border:1px solid var(--line);border-radius:14px;overflow:hidden}}.toolbar{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:20px 24px;border-bottom:1px solid var(--line)}}h2{{font-size:18px;margin:0 auto 0 0}}input,select{{border:1px solid #cbd8db;border-radius:7px;padding:9px 12px;font:inherit;background:white;color:var(--ink);max-width:100%}}.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;white-space:nowrap;font-size:13px}}thead{{background:#f3f7f6;color:var(--muted);font-size:11px}}th{{font-weight:600;text-align:left}}td,th{{padding:15px 13px;border-bottom:1px solid #edf1f1}}th:first-child,td:first-child{{padding-left:24px}}tbody tr:hover{{background:#f5fbf8}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.ticker{{display:block;font-size:11px;color:var(--muted);letter-spacing:.06em}}.rank{{color:#95a6ad;font-variant-numeric:tabular-nums}}.market{{font-size:10px;border:1px solid #dce5e6;border-radius:4px;padding:3px 6px}}.score{{color:var(--green);min-width:100px}}.bar{{display:block;height:3px;background:#e6eeea;margin-top:5px}}.bar i{{display:block;height:100%;background:#39b18b}}.empty{{text-align:center;white-space:normal;padding:65px 20px;color:var(--muted)}}.downloads{{padding:16px 24px;display:flex;gap:24px;align-items:center;font-size:12px}}.button{{border:1px solid #c6dbd3;border-radius:6px;padding:7px 12px}}.notes{{display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:30px;font-size:13px;color:var(--muted)}}.notes h3{{font-size:14px;color:var(--ink);margin:0 0 10px}}.notes p{{margin:8px 0}}.formula{{background:#eaf0ed;color:#285442;padding:12px 15px;border-radius:8px;font-variant-numeric:tabular-nums}}footer{{border-top:1px solid var(--line);margin-top:30px;padding-top:20px;font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:15px}}.muted{{color:var(--muted)}}#freshness{{font-size:12px;color:#9b671a;margin-top:8px}}.hidden{{display:none}}@media(max-width:740px){{main{{padding:26px 16px}}.hero{{display:block}}.date-box{{text-align:left;margin-top:22px}}.stats{{grid-template-columns:repeat(2,1fr);gap:10px}}.stat{{padding:14px 16px}}.notes{{grid-template-columns:1fr;gap:20px}}.toolbar{{padding:16px}}.toolbar h2{{width:100%}}input{{width:100%}}footer{{display:block}}}}
</style></head><body>
<header><div class="brand">KRX <span>RS</span> MONITOR</div><p>KOREA EQUITY · RELATIVE STRENGTH</p></header>
<main><section class="hero"><div><div class="eyebrow">DAILY MARKET SCREEN</div><h1>시장을 앞서는 종목들.</h1><p class="lede">KOSPI + KOSDAQ 통합 상대강도 · 거래대금 조건을 통과한 TOP {settings['top']}</p></div>
<div class="date-box"><span class="pill">평일 21:00 KST 수집 시작</span><div>데이터 기준일</div><strong>{e(as_of)}</strong><div>갱신 {e(generated)}</div><div id="freshness" data-date="{e(meta['as_of'] if meta else '')}"></div></div></section>
<section class="stats" aria-label="수집 요약"><div class="stat"><span>전체 종목</span><b>{format(stats['universe'], ',') if 'universe' in stats else '—'}</b><small>KOSPI + KOSDAQ</small></div><div class="stat"><span>계산 대상</span><b>{format(stats['eligible'], ',') if 'eligible' in stats else '—'}</b><small>61거래일 유효 수정종가</small></div><div class="stat"><span>조건 충족</span><b>{format(stats['matched'], ',') if 'matched' in stats else '—'}</b><small>거래대금 · RS 필터 통과</small></div><div class="stat"><span>표시 종목</span><b>{format(stats['displayed'], ',') if 'displayed' in stats else '—'}</b><small>RS Score 내림차순</small></div></section>
<section class="panel"><div class="toolbar"><h2>상대강도 순위</h2><label><span class="hidden">시장</span><select id="market" aria-label="시장 선택"><option value="">전체 시장</option><option>KOSPI</option><option>KOSDAQ</option></select></label><input id="search" type="search" placeholder="종목명 또는 코드 검색" aria-label="종목 검색"></div>
<div class="table-wrap"><table><thead><tr><th>#</th><th>종목</th><th>시장</th><th>RS Score</th><th class="num">RS1</th><th class="num">RS5</th><th class="num">RS20</th><th class="num">RS60</th><th class="num">20일 평균 · 억원</th><th class="num">당일 · 억원</th></tr></thead><tbody>{table}</tbody></table><p id="no-match" class="empty hidden">검색 조건에 맞는 종목이 없습니다.</p></div><div class="downloads">{downloads}</div></section>
<section class="notes"><div><h3>어떤 종목이 표시되나요?</h3><p>20일 평균 거래대금 ≥ {settings['avg_turnover_min']/1e8:g}억원 · 당일 ≥ {settings['turnover_min']/1e8:g}억원<br>RS20 ≥ {settings['rs20_min']:g} · RS5 ≥ {settings['rs5_min']:g}</p><p>전체 유효 종목의 수익률 백분위를 계산한 뒤 필터를 적용합니다. 평균 거래대금에는 기준일이 포함됩니다. 동점은 평균 순위로 계산합니다.</p></div><div><h3>RS Score 계산</h3><div class="formula">{formula}</div><p>RS1·5·20·60은 각 기간 수정종가 수익률의 백분위입니다. 신규 상장 등 61거래일 데이터가 부족한 종목은 제외합니다. 휴장일에는 직전 결과를 유지하며 수집 실패 시 기존 페이지를 보존합니다.</p></div></section>
<footer><span>데이터: pykrx (KRX / Naver) · 학습용 스크리너 · 투자 권유가 아닙니다.</span><a href="{REPO}/actions">수집·배포 상태 ↗</a></footer></main>
<script>
const search=document.querySelector('#search'), market=document.querySelector('#market'), rows=[...document.querySelectorAll('tr[data-market]')];
function filter(){{let n=0;rows.forEach(r=>{{const ok=(!market.value||r.dataset.market===market.value)&&r.textContent.toLowerCase().includes(search.value.trim().toLowerCase());r.hidden=!ok;if(ok)n++;}});document.querySelector('#no-match').classList.toggle('hidden',!rows.length||n>0);}}
search.addEventListener('input',filter);market.addEventListener('change',filter);
const freshness=document.querySelector('#freshness');if(freshness.dataset.date){{const days=(Date.now()-Date.parse(freshness.dataset.date+'T15:30:00+09:00'))/86400000;if(days>4)freshness.textContent='최근 거래일 또는 수집·배포 상태를 확인하세요.';}}
</script></body></html>'''
    destination.mkdir(parents=True, exist_ok=True)
    if meta:
        for prefix in ("top20", "ranked"):
            shutil.copyfile(source / f"{prefix}-{as_of}.csv", destination / f"{prefix}-{as_of}.csv")
        # Publish only metadata produced by our application, never cache or credentials.
        (destination / "latest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / ".nojekyll").touch()
    temporary = destination / "index.html.tmp"
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(destination / "index.html")
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("output"))
    parser.add_argument("--destination", type=Path, default=Path("docs"))
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    render(args.source, args.destination, allow_empty=args.allow_empty)


if __name__ == "__main__":
    main()
