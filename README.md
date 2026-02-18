# Food List Uploader

이미지 업로드 후 SHA256 해시 기반 중복 판별, Gemini 품목 추출, 정규화/카테고리/예상소비기한 계산, Google Sheets 적재까지 수행하는 FastAPI 프로젝트입니다.

## 프로젝트 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /metrics, /upload, /web)
  core/config.py           # .env 기반 설정
  core/logging_config.py   # 로깅 설정
  db/cache.py              # SQLite 초기화/업로드 메타데이터 저장
  services/                # Gemini/Sheets/정규화 서비스
  utils/hash_utils.py      # 이미지 SHA256 해시 계산
  main.py                  # FastAPI 앱 엔트리

tests/                     # pytest 테스트
.github/workflows/ci.yml   # Ruff/Black/Pytest CI
Dockerfile                 # FastAPI 컨테이너 이미지
```

## 환경 변수 설정

1. 예시 파일 복사

```bash
cp .env.example .env
```

2. `.env`에 아래 필수 값 입력

- `UPLOAD_TOKEN`: `/upload` 인증 헤더(`X-Upload-Token`) 값
- `SPREADSHEET_ID`: 대상 Google Spreadsheet ID (`GOOGLE_SHEET_ID`도 하위 호환)
- `GOOGLE_CREDENTIALS_JSON`: 서비스 계정 JSON 문자열 또는 JSON 파일 경로

선택 값:

- `SHEET_NAME` (기본값: `Fridge`)
- `IMAGE_RETENTION_DAYS`
- `DB_PATH`

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## 코드 위생(포맷/린트/테스트)

이 저장소는 `pyproject.toml` 기반으로 포맷/린트 규칙을 관리합니다.

```bash
pip install -r requirements-dev.txt
black .
ruff check .
black --check .
pytest -q
```

## Docker 실행

### Dockerfile 사용

```bash
docker build -t food-list-uploader .
docker run --rm -p 8000:8000 --env-file .env -v "$(pwd)/data:/app/data" food-list-uploader
```

### docker-compose 사용(선택)

```bash
docker compose up --build
```

## CI

GitHub Actions (`.github/workflows/ci.yml`)에서 아래를 자동 검증합니다.

1. `ruff check .`
2. `black --check .`
3. `pytest -q`

## 주요 API

### `GET /health`

```bash
curl -X GET "http://127.0.0.1:8000/health"
```

### `GET /metrics`

```bash
curl -X GET "http://127.0.0.1:8000/metrics"
```

### `GET /web`

```bash
curl -X GET "http://127.0.0.1:8000/web"
```

### `POST /upload`

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -H "X-Upload-Token: ${UPLOAD_TOKEN}" \
  -F "file=@/path/to/image.jpg;type=image/jpeg"
```
