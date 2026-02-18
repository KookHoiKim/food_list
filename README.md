# Food List Uploader

이미지 파일 업로드 후 SHA256 해시 기반 중복 판별, Gemini 품목 추출, 정규화/카테고리/예상소비기한 계산, Google Sheets 적재까지 한 번에 수행하는 FastAPI 프로젝트입니다.

## 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /metrics, /upload, /web)
  core/config.py           # .env 기반 설정
  core/logging_config.py   # 로깅 설정
  db/cache.py              # SQLite 초기화/업로드 메타데이터 저장
  utils/hash_utils.py      # 이미지 SHA256 해시 계산
  main.py                  # FastAPI 앱 엔트리
data/uploads/              # 저장된 업로드 파일 ({hash}.jpg)
```

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## DB 초기화 (migrations 없이)

앱 시작 시 `init_db()`가 실행되며 SQLite에 `uploads` 테이블을 자동 생성합니다.

```sql
CREATE TABLE IF NOT EXISTS uploads (
  hash TEXT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  original_filename TEXT,
  size_bytes INTEGER NOT NULL
);
```


## Gemini 추출 스키마 (단일 경로)

Gemini 추출은 **`app/services/gemini_client.py` 단일 모듈**로 통합되어 있습니다.
`/upload`는 `extract_items_from_image(...)`만 사용합니다.

응답 스키마(모델 출력)는 JSON 배열입니다.

```json
[
  {
    "name_raw": "string",
    "qty": 1.0,
    "unit": "개",
    "confidence": 0.93
  },
  {
    "name_raw": "우유",
    "qty": null,
    "unit": null,
    "confidence": 0.44
  }
]
```

- `qty`, `unit`은 스크린샷 품질/문맥에 따라 `null` 허용
- 서버 후처리로 `name_norm`, `category`, `storage`, `default_days`, `expiry_estimated`가 자동 계산

## API

### `GET /health`

```bash
curl -X GET "http://127.0.0.1:8000/health"
```

응답 예시:

```json
{"status":"ok"}
```

### `GET /metrics`

운영 관측을 위한 간단한 JSON 지표를 제공합니다.

```bash
curl -X GET "http://127.0.0.1:8000/metrics"
```

응답 예시:

```json
{
  "total_uploads": 120,
  "duplicates": 18,
  "gemini_calls": 95,
  "sheets_append_success": 94,
  "sheets_append_failure": 1,
  "avg_processing_seconds": 1.327
}
```

### `GET /web`

모바일 업로드 테스트를 위한 간단한 HTML 페이지입니다.

- 토큰 입력(`X-Upload-Token`)
- 이미지 선택 후 업로드 버튼
- 업로드 결과: 추출 품목 프리뷰 + 구글 시트 링크 표시

```bash
curl -X GET "http://127.0.0.1:8000/web"
```

### `POST /upload`

- 요청 타입: `multipart/form-data`
- 필드명: `file`
- 지원 포맷: `image/jpeg`, `image/png`
- 업로드 크기 제한: 최대 10MB
- 인증: 헤더 `X-Upload-Token` 필수 (값은 `.env`의 `UPLOAD_TOKEN`)
- 처리 단계: `해시/저장 -> Gemini 추출(통합 gemini_client) -> 후처리 필드 사용 -> Google Sheets append`
- 단계별 처리 시간 로그와 전체 `processing_seconds`를 응답에 포함

#### 업로드 예시

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -H "X-Upload-Token: ${UPLOAD_TOKEN}" \
  -F "file=@/path/to/image.jpg;type=image/jpeg"
```

#### 중복일 때 응답 예시

```json
{
  "duplicate": true,
  "num_items_extracted": 0,
  "num_rows_appended": 0,
  "sheet": {"spreadsheet_id": "<id>", "sheet_name": "Fridge"},
  "items_preview": [],
  "processing_seconds": 0.012
}
```

#### 신규 업로드 응답 예시

```json
{
  "duplicate": false,
  "num_items_extracted": 4,
  "num_rows_appended": 4,
  "sheet": {"spreadsheet_id": "<id>", "sheet_name": "Fridge"},
  "items_preview": [
    {
      "name_raw": "우유 1L",
      "name_norm": "우유",
      "qty": 1,
      "unit": "개",
      "category": "dairy",
      "storage": "냉장",
      "expiry_estimated": "2025-01-17"
    }
  ],
  "processing_seconds": 1.274
}
```

#### 실패 응답(stage 포함) 예시

```json
{
  "stage": "validate_input",
  "message": "Only JPG and PNG files are supported",
  "processing_seconds": 0.003
}
```

실패 시 가능한 `stage` 값:

- `validate_input`
- `hash_and_save`
- `gemini_extract`
- `normalize_items`
- `append_sheet`
- `unknown`

## Google Sheets 저장(서비스 계정)

`app/services/sheets_client.py`는 Google Sheets를 주 저장소로 사용하기 위한 클라이언트입니다.

### 필수 환경변수

- `SPREADSHEET_ID`: 대상 스프레드시트 ID
- `SHEET_NAME`: 시트 이름 (기본값 `Fridge`)
- `GOOGLE_CREDENTIALS_JSON`: 서비스 계정 JSON 문자열 또는 JSON 파일 경로
- `UPLOAD_TOKEN`: `/upload` 요청 인증용 토큰 (`X-Upload-Token` 헤더)

> 하위 호환: 기존 `GOOGLE_SHEET_ID`도 `SPREADSHEET_ID` 대신 사용할 수 있습니다.

### Google Cloud 설정 요약

1. Google Cloud에서 프로젝트 생성
2. **Google Sheets API** 활성화
3. 서비스 계정 생성 후 JSON 키 발급
4. 대상 스프레드시트를 서비스 계정 이메일에 편집자(Editor)로 공유
5. 발급받은 JSON 전체를 `GOOGLE_CREDENTIALS_JSON`에 넣거나 파일 경로로 지정

### 사용 예시

```python
from app.services.sheets_client import SheetsClient

client = SheetsClient()
client.ensure_header()

rows = [
    {
        "id": "item-001",
        "added_at": "2025-01-10T10:30:00",
        "purchase_date": "2025-01-10",
        "name_raw": "서울우유 1L",
        "name_norm": "서울우유",
        "qty": 1,
        "unit": "개",
        "storage": "냉장",
        "category": "dairy",
        "default_days": 7,
        "expiry_estimated": "2025-01-17",
        "expiry_override": "",
        "status": "active",
        "source": "gemini",
        "source_hash": "sha256:abc123",
        "note": "",
    }
]

# upload 단위 중복은 SQLite(hash PRIMARY KEY)에서 먼저 차단
client.append_rows(rows)
```

- `ensure_header()`: 시트 첫 행이 비어 있으면 자동으로 헤더(`id ... note`)를 작성합니다.
- 업로드 중복 방지는 SQLite `uploads.hash`(PRIMARY KEY)에서 처리합니다.
- `append_rows(...)`: `values.append` + `valueInputOption=USER_ENTERED`로 전달된 행을 그대로 추가합니다.
  같은 업로드(`source_hash`)에서 여러 품목이 추출되면 모두 append됩니다.


### 품목 수정/정리 API

기존 행을 수동으로 수정하지 않고 서버 API로 상태/메모/유통기한 오버라이드를 갱신할 수 있습니다.

- 엔드포인트: `PATCH /items/{id}`
- 본문(JSON, 모두 optional):
  - `status`: `active | used | removed | discarded`
  - `expiry_override`: `YYYY-MM-DD` 또는 `""`(빈 문자열, 값 초기화)
  - `note`: 문자열
- 동작: `id` 컬럼에서 대상 행을 찾아 **요청한 필드만** 업데이트
- 에러: 대상 `id`가 없으면 `404`

예시:

```bash
curl -X PATCH "http://localhost:8000/items/item-001" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "used",
    "expiry_override": "",
    "note": "2025-01-15 사용완료"
  }'
```

## iOS 단축어: 공유 → 서버 업로드 구성 방법

아래 순서로 iPhone 기본 **단축어(Shortcuts)** 앱에서 구성하면, 사진 공유 시 서버로 바로 업로드할 수 있습니다.

1. 단축어 앱에서 새 단축어 생성
2. 우측 상단 정보(ⓘ) > **공유 시트에서 표시** 활성화
3. 수신 유형을 **이미지**로 설정
4. 동작 추가: **URL**
   - 값: `https://<서버도메인>/upload`
5. 동작 추가: **텍스트**
   - 값: `.env`의 `UPLOAD_TOKEN` 값
6. 동작 추가: **사전(Dictionary)**
   - 키: `X-Upload-Token`
   - 값: 5번 텍스트
7. 동작 추가: **URL의 내용 가져오기(Get Contents of URL)**
   - 메서드: `POST`
   - 요청 본문: `폼(Form)`
   - 폼 필드 추가
     - 키: `file`
     - 타입: `파일(File)`
     - 값: 단축어 입력(공유로 받은 이미지)
   - 헤더: 6번 Dictionary 지정
8. 동작 추가: **빠른 보기(Quick Look)** 또는 **결과 보기**
   - 서버 JSON 응답(`items_preview`, `sheet`) 확인

팁:
- 서버가 사설망에 있다면 iPhone에서 같은 네트워크/VPN에 연결되어야 합니다.
- 보안을 위해 `UPLOAD_TOKEN`은 길고 추측 어려운 문자열로 설정하세요.

## 운영/보안/비용 가이드

### 운영(Observability)
- `/metrics`에서 업로드/중복/Gemini 호출/Sheets append 성공·실패/평균 처리시간을 확인할 수 있습니다.
- 앱 시작 시 이미지 보관 정책 정리 작업이 1회 실행되며, 이후 **하루 1회** 자동 실행됩니다(APScheduler interval).

### 보안/프라이버시(이미지 자동 삭제)
- 업로드 이미지는 `IMAGE_RETENTION_DAYS`(기본값 `7`) 기준으로 자동 정리됩니다.
- 정리 시 업로드 파일(`data/uploads/{hash}.jpg|png`)과 SQLite `uploads` 메타데이터를 함께 삭제합니다.
- 스케줄러를 쓰지 않는 환경(예: 서버리스/단일 스크립트 실행)에서는 cron으로 `cleanup_old_uploads()`에 해당하는 배치 실행을 권장합니다.

### 비용(Gemini 호출 제어)
- 중복 업로드는 Gemini 호출을 하지 않습니다.
- 신규 업로드라도 이미지가 `GEMINI_INLINE_MAX_BYTES`(기본 4MB)를 초과하면 인라인 전송 대신 실패 처리하고 경고 로그를 남깁니다.
- 4MB 초과 로그에는 `TODO: Gemini File API` 전환 필요 메시지가 포함됩니다.

### 신규 환경변수
- `IMAGE_RETENTION_DAYS=7`
- `GEMINI_INLINE_MAX_BYTES=4194304`

