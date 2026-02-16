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
