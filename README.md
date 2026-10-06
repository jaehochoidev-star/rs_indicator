# rs_indicator / krx-rs-monitor

KOSPI + KOSDAQ 일별 상대강도(RS) 스크리너 1단계 MVP.

## 실행 (Windows PowerShell)

Python 3.11 이상이 필요합니다. 현재 저장소에는 전용 `.venv`를 구성했습니다.

```powershell
cd D:\ChatGPT-GitHub\rs_indicator
# 새 환경에서 처음 설치할 때:
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 최근 완료된 거래일 (한국시간 18시 이전에는 전일까지)
.\.venv\Scripts\python.exe -m krx_rs_monitor
# 재현 가능한 기준일 지정
.\.venv\Scripts\python.exe -m krx_rs_monitor --date 2026-10-05
# 계정 정보를 저장하지 않고 현재 실행에만 입력 (비밀번호 표시 안 함)
.\.venv\Scripts\python.exe -m krx_rs_monitor --login --date 2026-10-05
.\.venv\Scripts\python.exe -m pytest -q
```

pykrx의 KRX 조회에 인증이 필요한 경우 실행 프로세스에 `KRX_ID`, `KRX_PW` 환경변수를 설정하세요. 비밀번호는 소스·명령 기록·Git에 저장하지 마세요. `.env`는 자동 로딩하지 않습니다. pykrx 문서: <https://github.com/sharebook-kr/pykrx>.

현재 어댑터는 인증 환경변수가 없으면 조회 전에 종료합니다. 로컬에서는 `--login`으로 입력하고, 향후 GitHub Actions에서는 저장소 Settings → Secrets and variables → Actions에 `KRX_ID`, `KRX_PW`를 등록해 작업의 환경변수에 연결합니다. GitHub Secrets는 로컬 PC에서 다운로드해 사용할 수 없습니다.

첫 수집은 전체 종목의 수정종가를 개별 조회하므로 **수십 분 이상** 걸릴 수 있습니다. 호출 사이에 최소 1초를 두고 순차 수집합니다. 성공한 응답은 `data/cache/`에 저장되며 동일 기준일 재실행 시 이어서 활용합니다. `--refresh`는 캐시를 무시합니다. 수정주가 캐시는 기준일마다 분리합니다.

## 계산 정의

- 대상: 기준일 KOSPI + KOSDAQ 종목을 통합. KONEX·ETF·ETN 제외, 우선주·SPAC은 포함.
- KOSPI 지수 일별 시계열에서 거래일을 확인하고 61거래일 수정종가를 수집합니다. 휴일은 직전 거래일로 해석하고 실제 기준일을 출력합니다. 10일 넘게 오래된 달력은 오류 처리합니다.
- `returnN = (기준일 수정종가 / N거래일 전 수정종가 - 1) × 100`, N=1/5/20/60.
- 61개 종가 중 결측·0·비정상 값이 있는 종목은 전체 기간의 순위 모집단에서 제외합니다. 신규 상장 종목을 임의로 보간하지 않습니다.
- `RSN = 평균 순위 / 유효 종목 수 × 100`. 수익률이 높을수록 높은 점수. 동점은 평균 순위. 범위는 0 초과~100이며, 전 종목 동점이면 100점이 아닙니다.
- `RS Score = RS1×0.10 + RS5×0.30 + RS20×0.40 + RS60×0.20`.
- **전체 유효 종목의 백분위를 먼저 계산**한 다음 20거래일 평균 거래대금 ≥ 50억원, 당일 거래대금 ≥ 100억원, RS20 ≥ 90, RS5 ≥ 90을 모두 적용합니다.
- 평균 거래대금은 기준일 포함 20거래일의 실제 거래대금(원)이며 종가×거래량으로 추정하지 않습니다. 거래정지일의 실제 거래대금 0도 평균에 포함합니다.
- RS Score → RS20 → RS5 → 당일 거래대금 내림차순, 마지막 동점은 종목코드 오름차순으로 TOP20을 출력합니다. 조건 충족 종목이 20개 미만이면 해당 개수만 출력합니다.
- 수집 실패·빈 응답·한 시장 누락·유효 종목의 거래대금 결측은 성공으로 처리하지 않으며 종료 코드 2를 반환합니다. 정상적으로 조건 충족 종목이 없는 경우는 종료 코드 0입니다.

## 옵션과 결과

```powershell
.\.venv\Scripts\python.exe -m krx_rs_monitor --weights 10 30 40 20 --top 20
```

`--avg-turnover`, `--today-turnover`는 원 단위이며 `--rs20-min`, `--rs5-min`, `--date`, `--cache-dir`, `--output-dir`, `--timeout`, `--refresh`도 지원합니다.

- `output/top20-YYYY-MM-DD.csv`: 조건 충족 TOP20 (UTF-8 BOM)
- `output/ranked-YYYY-MM-DD.csv`: 전체 유효 종목의 수익률·RS·필터 통과 여부
- `output/run-YYYY-MM-DD.json`: 실제 기준일·생성 시각·설정·모집단·제외 수·통과 수

실패한 실행은 새 결과를 발행하지 않습니다. 이전 성공 결과 파일이 남아 있을 수 있으므로 JSON의 `generated_at`과 실행 종료 코드를 확인하세요. CSV의 종목코드는 스프레드시트에서 텍스트로 읽어야 앞자리 0이 보존됩니다.

## 구조와 확장

```text
src/krx_rs_monitor/
  models.py           MarketData / MarketDataProvider 계약
  providers/pykrx.py  pykrx 수집·타임아웃·재시도·캐시
  scoring.py          공급자와 독립적인 RS 계산·필터
  cli.py              실행·CSV·실행 메타데이터
tests/                 계산 및 수집 실패 검증
```

KRX 공식 Open API로 전환할 때 `MarketDataProvider.collect(requested)`를 구현하여 기준일, 공통 거래일, 종목 목록, 수정종가, 실제 거래대금 행렬을 반환하면 계산기는 그대로 사용합니다. 공식 API의 원시 종가만으로 대체할 경우 기업행사에 대한 수정주가 처리가 별도로 필요합니다.

## 자동 실행과 GitHub Pages

- 웹사이트: https://jaehochoidev-star.github.io/rs_indicator/
- 실행 상태: https://github.com/jaehochoidev-star/rs_indicator/actions
- `.github/workflows/monitor.yml`이 월~금 **21:00 KST (UTC 12:00)**에 수집을 시작합니다. GitHub 예약 작업은 혼잡할 때 지연될 수 있으며, 페이지는 전체 수집 완료 후 갱신됩니다. 현재 전체 수집은 2,700여 종목의 순차 조회로 약 1시간 이상 소요될 수 있습니다.
- GitHub 서버에서 실행되므로 PC를 켜둘 필요가 없습니다. 저장소의 Actions Secrets `KRX_ID`, `KRX_PW`를 사용합니다. 비밀번호를 공개 파일이나 페이지에 저장하지 않습니다.
- 휴장일에는 종목별 수집과 재배포를 건너뜁니다. 조회 실패 시 작업이 실패로 표시되고 기존 페이지는 유지됩니다. 화면의 기준일과 갱신 시각, Actions 상태를 확인하세요.
- 수동 실행: Actions → **RS Monitor & GitHub Pages** → Run workflow. `date`를 비워두면 최신 완료 날짜, 지정하면 해당 과거 날짜의 결과로 페이지를 갱신합니다.
- 소스 push는 테스트 후 `docs/`의 현재 페이지를 배포하며 전체 데이터를 재수집하지 않습니다.
- 페이지에는 TOP20, 각 기간 RS, 거래대금, 시장·종목 검색, CSV 다운로드가 포함됩니다. 순위 CSV와 요약 통계만 공개하고 원시 캐시·계정 정보는 게시하지 않습니다.
- 생성: `.\.venv\Scripts\python.exe -m krx_rs_monitor.dashboard`. 완료된 `output/run-날짜.json`과 CSV가 있어야 하며, 불완전한 결과는 게시하지 않습니다.
- Pages 설정은 GitHub Actions 방식입니다. Workflow는 `contents: write`(결과 보관), `pages: write`, `id-token: write`(배포)를 사용합니다.

남은 확장: 52주 신고가 거리, 최근 7거래일 RS 그래프, Telegram Bot.

종목명 앞에 기준일의 KRX 업종 분류를 표시합니다. 업종명으로 검색할 수 있으며 CSV에도 sector 열이 포함됩니다. 조회되지 않은 업종은 미분류로 표시합니다. 기존 게시 결과에는 업종만 보강하며 RS 점수와 순서는 변경하지 않습니다.
