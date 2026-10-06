# MVP 검증 기록 — 2026-10-06

## 저장소

- 로컬: `D:\ChatGPT-GitHub\rs_indicator`
- 원격: `https://github.com/jaehochoidev-star/rs_indicator.git`
- 시작 상태: `main`, 원격 추적 브랜치 `origin/main`, 변경 없음, README만 존재.
- 구현은 해당 로컬 저장소에 반영했으며 커밋·푸시는 수행하지 않았습니다.

## 실행 환경 및 자동 검증

- 저장소 전용 `.venv`, Python 3.12 계열, pykrx 1.2.9, pandas 2.3.3.
- 설치: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` 성공.
- 테스트: `.\.venv\Scripts\python.exe -m pytest -q`
- 결과: **20 passed in 3.99s**, 종료 코드 0.
- 검증 범위: 통합 모집단 백분위, 1/60일 수익률, 가중치 순서·정규화, 동점, 정확한 50억/100억 경계값, 필터 적용 순서, 신규 상장·결측 제외, 불완전 거래대금 오류, TOP20 개수 제한, 정상 0건, 날짜 마감 시각, CSV 출력, 오류 시 미발행, 캐시 재사용·종목코드 보존, 빈 응답 재시도, 모의 공급자의 주말 기준일 처리, 요청 타임아웃 복원, 인증 누락 안내.
- 테스트의 종목 및 가격은 **가상 데이터**입니다. 실제 시장 성과 검증이 아닙니다.

## 실제 데이터 실행

실행 명령:

```powershell
.\.venv\Scripts\python.exe -m krx_rs_monitor --date 2026-10-05
```

실제 pykrx 호출을 시도했으나 다음 문제로 거래일 조회부터 실패했습니다.

```text
KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다.
Collecting trading calendar through 2026-10-05 ...
Retry 1/2: 20261005/calendar-20260408
Retry 2/2: 20261005/calendar-20260408
ERROR: pykrx query failed: 20261005/calendar-20260408 (KeyError).
```

따라서 **실제 시장 데이터 수집과 TOP20 결과는 아직 검증되지 않았습니다.** KRX 계정 미보유를 사용자에게 확인했습니다. 인증이 준비된 뒤에도 공급자의 응답과 전체 시장 수집 성공을 확인해야 합니다.

이 실패 이후 인증 정보가 없으면 즉시 명확한 안내와 종료 코드 2를 반환하도록 개선했고, `--login` 입력 기능을 추가했습니다. 비밀번호는 입력 중 표시하지 않으며 파일에 기록하지 않습니다. pykrx가 초기화 중 출력하는 로그인 아이디도 프로그램 로그에 남기지 않습니다.

## 계정 준비 후 재검증

```powershell
cd D:\ChatGPT-GitHub\rs_indicator
.\.venv\Scripts\python.exe -m krx_rs_monitor --login --date 2026-10-05
```

첫 수집은 종목별 수정종가 조회로 수십 분 이상 걸릴 수 있습니다. 성공 시 실제 기준일, 모집단 및 제외 종목 수, 조건 충족 수, TOP20을 출력하고 `output/`에 CSV와 실행 메타데이터를 저장합니다.
