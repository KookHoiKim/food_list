# Food List Uploader

이미지 파일을 업로드하면 SHA256 해시 기반으로 중복을 판별하고, 처음 업로드된 파일만 로컬 저장 및 SQLite에 기록하는 FastAPI 프로젝트입니다.

## 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /upload)
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
- 중복(hash 존재) 시 파이프라인 스킵 후 `duplicate: true` 반환

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
  "hash": "<sha256>"
}
```

#### 신규 업로드 응답 예시

```json
{
  "duplicate": false,
  "hash": "<sha256>",
  "saved_path": "data/uploads/<sha256>.jpg",
  "size_bytes": 12345
}
```

#### 크기 제한 초과 예시

```json
{
  "detail": "File size exceeds limit (10MB)"
}
```

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
