# 북미 자산운용사 트래커

북미 자산운용사들이 **공개적으로 남기는 흔적**을 주기적으로 모아서, 지우지 않고 계속 쌓아두는 시스템입니다.

운용사별로 따로 추적하며, 모으는 것은 다섯 가지입니다.

| 무엇을 | 어디서 |
|---|---|
| **미국 보유종목** | SEC EDGAR 13F-HR (수정보고 포함) |
| **한국 보유종목** | 운용사 자체 펀드 공시(팩트시트) — 한국 대형주에 닿는 유일한 무료 경로 |
| **한국 5% 지분** | DART 대량보유상황보고 — 값싼 안전망으로 유지 |
| **AUM** | SEC Form ADV RAUM, 13F 합계, 홈페이지 표기 |
| **인력** | Form ADV Schedule A, 회사 팀 페이지 |

**현재 추적 중:** Burgundy, DRZ, Kopernik
**은퇴(등록은 유지):** Mawer, EdgePoint, Beutel Goodman, Letko Brosseau

---

## 이 시스템이 지키는 세 가지 원칙

코드 곳곳의 설계가 여기서 나옵니다. 먼저 읽으시면 나머지가 쉽게 이해됩니다.

### 1. 지우지 않습니다 (append-only)

수집한 데이터는 **수정하거나 삭제하지 않습니다.** 정정 공시나 수정보고가 오면 새 행으로 추가됩니다. 그래서 "그때 우리가 뭘 알고 있었나"를 항상 되짚을 수 있습니다.

### 2. 추측하지 않습니다

CIK, CRD, 웹사이트 주소 같은 식별자는 **확인된 것만** 넣습니다. 모르면 비워둡니다.

비워두면 해당 수집기가 그 운용사를 건너뛰고, 대시보드에 **"not configured"로 보입니다.** 반면 CIK를 잘못 넣으면 **다른 회사 포트폴리오가 이 운용사 이름으로 올라오는데, 화면상 아무 이상이 없습니다.** 되돌릴 수 있는 실수와 없는 실수의 차이입니다.

### 3. "없음"이 "아님"으로 읽히지 않게 합니다

이게 가장 중요하고, 실수가 가장 잦았던 부분입니다.

- 팩트시트에 삼성전자가 없다 → **"보유하지 않는다"가 아닙니다.** 상위 25종목만 인쇄되니까요
- 수집기가 빈 결과를 냈다 → **"공시가 없다"가 아닙니다.** 파싱이 실패했을 수도 있습니다
- EDGAR 검색이 0건이다 → **"제출하지 않았다"가 아닙니다.** 다른 CIK로 냈을 수도 있습니다

그래서 파서는 형식을 못 알아보면 **빈 목록 대신 예외를 던지고**, 화면은 "미수집"과 "없음"을 다르게 표시합니다.

---

## 데이터가 쌓이는 구조 (3계층)

```
raw_documents    원본 그대로 (XML/JSON/HTML/PDF) — 다시 받지 않고도 재처리 가능
      │
스냅샷 테이블     holdings · fund_holdings · kr_holdings · proxy_votes
                 aum_history · personnel · fund_snapshots
      │
changes          변화 이벤트 (NEW_POSITION, EXITED, STAKE_CHANGED, TITLE_CHANGED …)
```

**원본을 통째로 보관하는 이유:** 파서를 고쳤을 때 다시 받지 않고 재처리할 수 있습니다 (`pipeline.reparse`). 상대 서버에 부담도 안 주고, 이미 사라진 문서도 살아 있습니다.

### 날짜는 항상 세 종류를 구분합니다

| 컬럼 | 뜻 |
|---|---|
| `as_of_date` | 공시가 말하는 기준일 (예: 분기말) |
| `filed_at` | 실제로 제출된 날 |
| `fetched_at` | 우리가 받아온 시각 |

셋을 뭉개면 "6월 30일 기준 자료를 8월에 받았다"를 표현할 수 없습니다.

### 몇 번을 돌려도 안전합니다

각 수집기에 **중복 방지 키**가 있습니다 — EDGAR는 `accession_no`, DART는 `rcept_no`, 스크래핑은 내용 해시. 같은 걸 또 받아도 행이 늘지 않습니다.

`personnel`만 예외적으로 이력 관리 방식(SCD Type 2)을 씁니다 — `valid_from` / `valid_to`로 "언제부터 언제까지 그 직책이었나"를 남깁니다.

---

## 운용사 추가·관리

### 추가하기

`config.py`의 `MANAGERS`에 한 줄 추가하면 끝입니다. `pipeline.run`이 매번 DB와 맞춥니다.

```python
{
    "slug": "kopernik",
    "name": "Kopernik",
    "legal_name": "KOPERNIK GLOBAL INVESTORS, LLC",
    "cik": "0001599814",        # 확인된 것만. 모르면 None
    "crd": None,                # 없으면 Form ADV 건너뜀
    "website_aum_url": "https://www.kopernikglobal.com/",
    "website_team_url": None,   # 경로를 모르면 비워둠
    "dart_terms": ["Kopernik"],
    "sort_order": 60,
}
```

**CIK는 그 회사의 EDGAR 문서에서 직접 읽어오세요.** 이름 검색 결과로 넣지 마십시오 — 위 "원칙 2"의 이유입니다.

### 은퇴시키기

```python
"is_active": False,
```

플래그 하나가 두 가지를 동시에 합니다:

- `pipeline.run`이 활성 운용사만 순회 → **외부 조회 전면 중단**
- 대시보드 모든 탭이 활성 여부로 운용사를 해석 → **화면에서 사라짐**. URL에 `?manager=mawer`를 직접 쳐도 다른 운용사로 넘어갑니다

**데이터는 지우지 않습니다.** 다시 `True`로 바꾸면 이력 그대로 돌아옵니다. 백필에서 이름을 명시하면 은퇴한 운용사도 여전히 돌릴 수 있습니다(운영자의 명시적 판단이니까요).

### 서로 섞이지 않습니다

모든 스냅샷 테이블에 `manager_id`가 있고, 중복 방지 규칙이 전부 운용사 단위로 걸려 있습니다. 예를 들어 `aum_history`는 `(manager_id, as_of_date, source)` 기준이라, 두 운용사가 같은 분기를 보고해도 서로 덮어쓸 수 없습니다.

---

## 한국 보유종목

**이 부분은 문서를 먼저 읽어주세요.** 이미 조사하고 배제한 경로를 다시 파는 일이 없도록 근거를 남겨뒀습니다.

- **`docs/korea-holdings.md`** — 어떤 소스가 답할 수 있고 없는지, 각각의 근거
- **`docs/korea-holdings-buildout.md`** — 만들어온 이력. 어떤 판단이 나중에 **뒤집혔는지**

### 요약

**DART 5% 룰로는 대형주를 볼 수 없습니다.** 5%는 *발행사 지분율* 기준이라, 삼성전자 5%면 이 운용사들 전체 자산보다 큽니다. 구조적으로 소형주만 나옵니다.

**팩트시트로는 볼 수 있습니다.** 다만 상위 10~25종목만 인쇄됩니다. 그래서 이 시스템이 말할 수 있는 건 **"최소 이만큼은 보유한다"이지, "이게 전부다"나 "보유하지 않는다"가 아닙니다.**

Mawer 팩트시트 실측 기준:

```
펀드 규모        C$7,251.5M
전체 보유종목    72종목 (인쇄 24 / 미인쇄 48)
안 보이는 영역   41.3% = C$2,995M
가시성 하한      1.6% = C$116M   ← 이 밑은 존재해도 안 보임
확인된 한국      SK hynix 3.0% (C$217M), 삼성전자 2.8% (C$203M)
```

이 한계를 `fund_holdings.disclosure_scope` 컬럼이 데이터 자체에 담고, 화면에도 문장으로 씁니다.

### 5% 수집기 동작 방식

DART에는 "이 운용사가 뭘 갖고 있나"를 묻는 API가 없습니다. 그래서 **지분공시를 낸 발행사들을 훑어서**(`list.json`), 보고자 이름이 그 운용사의 `dart_terms`와 맞는 행만 남깁니다.

매일 도는 수집기는 최근 며칠만 봅니다. 추적 시작 전에 나온 공시는 못 봅니다 — 그건 `pipeline.backfill_kr --since 2015`로 따로 훑습니다.

`list.json`이 실패하면(키 거부, 할당량 초과) **빈 목록을 반환하지 않고 예외를 던집니다.** 안 그러면 "고장난 실행"과 "조용한 한 주"가 구분되지 않습니다.

---

## 로컬에서 돌리기

```bash
pip install -e '.[dev]'      # 테스트까지 하려면 [dev]
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/burgundy"
export SEC_USER_AGENT="burgundy-tracker your-email@example.com"

python -m db.migrate                       # 스키마 생성/업그레이드
python -m pipeline.backfill --since 2015   # 과거 13F 불러오기
python -m pipeline.run                     # 전체 수집 1회
uvicorn dashboard.app:app --reload         # http://localhost:8000

pytest
```

> **DB가 없으면 테스트 절반이 조용히 skip됩니다.** 통과한 것처럼 보이지만 실제로는 안 돈 겁니다. Postgres를 꼭 띄워두세요.

### 자주 쓰는 명령

| 명령 | 하는 일 |
|---|---|
| `python -m db.migrate` | 안 돌린 마이그레이션 적용 (몇 번 돌려도 안전) |
| `python -m pipeline.run` | 크론 진입점 — 모든 수집기 실행 |
| `python -m pipeline.backfill --since 2015 [--limit N]` | 과거 13F 채우기 |
| `python -m pipeline.backfill_kr --since 2015` | 과거 한국 5% 공시 채우기 |
| `python -m pipeline.reparse [--source edgar_13f]` | 보관된 원본으로 스냅샷 재생성 (재수집 없음) |
| `python -m pipeline.heal [--manager <slug>]` | 파생된 `13f_total` AUM 재계산 |

---

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `DATABASE_URL` | ✅ | Postgres 접속 문자열 (Railway는 자동 주입) |
| `SEC_USER_AGENT` | ✅ | `"burgundy-tracker you@example.com"` — SEC가 실제 연락처를 요구합니다 |
| `DART_API_KEY` | 한국용 | https://opendart.fss.or.kr 에서 발급 |
| `FIRM_CRD` | Form ADV용 | 없으면 Form ADV를 건너뜁니다 |
| `DASHBOARD_PASSWORD` | 선택 | 설정하면 대시보드에 HTTP Basic 인증 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 선택 | 변화 알림. 없으면 조용히 생략 |

---

## 배포 (Railway)

저장소 하나에 **서비스 두 개**를 띄웁니다. Postgres 플러그인과 환경변수는 공유하고, 각자 자기 설정 파일을 읽어서 시작 명령이 충돌하지 않습니다.

| 서비스 | 설정 파일 | 시작 명령 | 실행 |
|---|---|---|---|
| `dashboard` | `railway.json` (기본) | `db.migrate && uvicorn …` | 상시 |
| `collector` | `railway.collector.json` | `db.migrate && pipeline.run` | 크론 `0 22 * * *` (UTC 22시 = 한국 07시) |

**설정 순서**

1. 이 저장소로 Railway 프로젝트를 만들고 **PostgreSQL** 플러그인 추가
2. `dashboard` 서비스는 `railway.json`으로 자동 배포됩니다. Settings → Networking에서 도메인 생성
3. 같은 저장소로 `collector` 서비스를 하나 더 추가. Settings → Config-as-code에서 **Railway Config File**을 `railway.collector.json`로 지정하면 시작 명령과 크론이 그 파일에서 옵니다. **도메인은 만들지 마세요**
4. 두 서비스 모두에 위 환경변수 설정

### 일회성 작업 돌리기

collector는 크론 서비스라 평소엔 정해진 시각에만 돕니다. 지금 당장 뭔가 한 번 돌리려면, collector의 **Config File**을 아래 중 하나로 바꿔 배포하고 **끝나면 원래대로 되돌립니다.** (크론 설정이 없어서 배포 시 한 번 돌고 종료됩니다.)

| 파일 | 하는 일 |
|---|---|
| `railway.backfill.json` | 과거 13F 적재 + 각 운용사 `13f_total` AUM 보정까지 |
| `railway.backfill_kr.json` | 과거 한국 5% 공시 적재. `KR_BACKFILL_SINCE` 등으로 범위 지정 |
| `railway.heal.json` | 저장된 보유내역으로 `13f_total` AUM 재계산. DB만 건드려서 수년치가 몇 초 |
| `railway.reparse.json` | 원본 재파싱. 파서를 고쳤을 때 재수집 없이 반영 |

> ⚠️ **main에 머지하면 collector가 재배포됩니다.** 그때 설정 파일이 가리키는 작업이 다시 시작됩니다. 긴 백필이 이 때문에 두 번 죽었습니다. **머지 전에 설정 파일을 되돌려 놓으세요.**
>
> 한국 백필은 이제 `--since` / `KR_BACKFILL_SINCE`를 명시하지 않으면 **아예 시작하지 않습니다.** 무관한 배포에 스스로 재시작하던 문제를 막기 위해서입니다.

백필 옵션은 시작 명령이 고정이라 환경변수로 받습니다:

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `BACKFILL_MANAGER` | `all` | 대상 운용사 slug, 또는 `all` |
| `BACKFILL_SINCE` | `2013` | 가장 오래된 보고 연도 |
| `BACKFILL_LIMIT` | 없음 | 이번 실행에서 운용사당 최대 건수 |

새로 추가한 운용사 하나만 채우려면 `BACKFILL_MANAGER=kopernik`으로 한 번 배포하면 됩니다. 백필은 몇 번 돌려도 안전하고, 운용사끼리 독립적이라 **하나가 실패해도 나머지는 계속 돕니다** — 실행은 실패 코드로 끝나면서 누가 실패했는지 이름을 남깁니다.

### 수집 주기

collector가 내부에서 갈라집니다:

- **매번**: EDGAR 13F, DART
- **주 1회**: Form ADV, 웹사이트 스크래핑, 팩트시트 (마지막 성공이 7일 이내면 건너뜀)

성공·건너뜀·실패 **모두** `collector_runs`에 기록됩니다. 대시보드에서 확인할 수 있습니다.

> **판독법:** `factsheet` 행에서 `new_raw > 0`인데 `new_rows = 0`이면, 문서는 받았지만 그 운용사 레이아웃이 아직 보정되지 않은 것입니다. `new_raw`도 0이면 아직 안 돈 겁니다. 둘은 다른 상황입니다.

---

## 대시보드 화면

| 탭 | 내용 |
|---|---|
| **Overview** | AUM 추이(소스별) · 최근 변화 · 수집기 실행 이력 |
| **AUM** | 관측값 전체를 출처와 함께. 자릿수 이상치는 따로 표시 |
| **US Holdings** | 최근 분기 보유종목(비중순), 전분기 대비 증감, 분기 선택 |
| **Korea** | 선택한 운용사의 한국 보유종목 — 비중, **환산 금액**, 근거 구분 |
| **Changes** | 전체 변화 타임라인, 유형 필터 |

### Korea 탭 읽는 법

한 종목마다 **근거**가 붙습니다. 소스마다 볼 수 있는 것이 달라서입니다.

| 근거 | 뜻 |
|---|---|
| 보유 확인 + 규모 | 팩트시트와 의결권 기록 양쪽에 있음 |
| 보유 확인 · 팩트시트 하한 미만 | 의결권 기록에만 있음 → **보유는 확실하나 C$116M 미만** |
| 팩트시트만 | 의결권 기록 기간(약 14개월 지연) 이후 신규 편입. 정상입니다 |

비중 옆에는 **환산 금액**이 같이 나옵니다. "3%"만으로는 3천만인지 3억인지 알 수 없으니, 펀드 규모를 곱해서 보여줍니다.

---

## 알아둘 한계

- **한국 보유종목은 하한입니다.** 팩트시트가 상위 N종목만 인쇄하므로, 표에 없다고 미보유가 아닙니다. 반대로 안 보이는 종목이 인쇄된 최소 비중을 넘을 수는 없으니, 사각지대의 크기는 알고 있습니다.
- **사모펀드·일임 계정은 어떤 무료 소스에도 안 나옵니다.** 팩트시트, MRFP, 의결권 기록 모두 공모 펀드만 다룹니다.
- **13F는 미국 상장 롱 포지션만** 담습니다. 공매도·현금·비미국 증권은 없습니다. 삼성전자·SK하이닉스는 미국 상장이 없어 13F에 절대 안 나옵니다.
- **Burgundy 보고 방식 변경 (2025년 4분기):** Burgundy가 자체 13F-HR 대신 13F-NT(통지)를 제출하기 시작했고, 미국 보유내역은 **Bank of Montreal**이 통합 신고합니다. 통합 신고분에서 Burgundy 몫만 떼어낼 수 없어, 단독 미국 보유내역과 파생 `13f_total` AUM은 **2025-09-30에서 멈춥니다.** 수집기가 이 통지를 `filing_notices`에 기록하고 대시보드가 배너로 설명합니다. Form ADV RAUM과 홈페이지 AUM은 별개로 계속 갱신됩니다.

---

## 코드 구조

```
config.py            # MANAGERS · FUNDS 레지스트리 (CIK, CRD, URL, DART 검색어) + 상수
db/                  # migrate.py 실행기 + migrations/
collectors/          # BaseCollector + edgar_13f / dart_5pct / factsheet / form_adv / website
parsers/             # 순수 함수: parse_13f / parse_dart / parse_factsheet /
                     #            parse_website / securities
pipeline/            # run.py(크론) · diff.py · backfill.py · reparse.py · repo.py · notify.py
dashboard/           # FastAPI + Jinja2 + HTMX + Chart.js
tests/               # 픽스처 + 파서/diff 테스트
docs/                # korea-holdings.md (소스 분석) · korea-holdings-buildout.md (이력)
```
