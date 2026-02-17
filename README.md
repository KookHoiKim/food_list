# Food List Uploader

이미지 파일 업로드 후 SHA256 해시 기반 중복 판별, Gemini 품목 추출, 정규화/카테고리/예상소비기한 계산, Google Sheets 적재까지 한 번에 수행하는 FastAPI 프로젝트입니다.

## 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /upload 통합 파이프라인)
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

## API

### `GET /health`

```bash
curl -X GET "http://127.0.0.1:8000/health"
```

응답 예시:

```json
{"status":"ok"}
```

### `POST /upload`

- 요청 타입: `multipart/form-data`
- 필드명: `file`
- 지원 포맷: `image/jpeg`, `image/png`
- 업로드 크기 제한: 최대 10MB
- 처리 단계: `해시/저장 -> Gemini 추출 -> 정규화/카테고리/expiry_estimated 계산 -> Google Sheets append`
- 단계별 처리 시간 로그와 전체 `processing_seconds`를 응답에 포함

#### 업로드 예시

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
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

# append 전 최근 N행(source_hash) 중복 확인 후 중복이면 스킵
client.append_rows(rows, lookback_rows=200)
```

- `ensure_header()`: 시트 첫 행이 비어 있으면 자동으로 헤더(`id ... note`)를 작성합니다.
- `has_hash_recently(source_hash, lookback_rows=200)`: 최근 N행에서 `source_hash` 중복 여부를 확인합니다.
- `append_rows(...)`: `values.append` + `valueInputOption=USER_ENTERED`로 행을 추가하며,
  중복 해시는 자동 스킵합니다.
