# Food List Uploader

이미지 파일 업로드 후 SHA256 해시 기반 중복 판별, Gemini 품목 추출, 정규화/카테고리/예상소비기한 계산, Google Sheets 적재까지 한 번에 수행하는 FastAPI 프로젝트입니다.

## 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /upload, /web)
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
- 처리 단계: `해시/저장 -> Gemini 추출 -> 정규화/카테고리/expiry_estimated 계산 -> Google Sheets append`
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

# append 전 최근 N행(source_hash) 중복 확인 후 중복이면 스킵
client.append_rows(rows, lookback_rows=200)
```

- `ensure_header()`: 시트 첫 행이 비어 있으면 자동으로 헤더(`id ... note`)를 작성합니다.
- `has_hash_recently(source_hash, lookback_rows=200)`: 최근 N행에서 `source_hash` 중복 여부를 확인합니다.
- `append_rows(...)`: `values.append` + `valueInputOption=USER_ENTERED`로 행을 추가하며,
  중복 해시는 자동 스킵합니다.

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
