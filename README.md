# Food List Uploader

모바일 스크린샷 이미지를 업로드하면 Gemini API로 품목 리스트를 추출하고 Google Sheets(`Inventory`)에 append하는 FastAPI 프로젝트입니다.

## 구조

```text
app/
  api/routes.py            # 라우팅 (/health, /upload)
  core/config.py           # .env 기반 설정
  core/logging_config.py   # 로깅 설정
  db/cache.py              # SQLite 캐시(중복 업로드 방지)
  models/inventory.py      # JSON 스키마 모델
  services/gemini.py       # Gemini API 호출
  services/sheets.py       # Google Sheets append
  utils/hash_utils.py      # 이미지 해시 계산
  main.py                  # FastAPI 앱 엔트리
tests/
  test_hash_utils.py
  test_inventory_schema.py
```

## 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

## 테스트

```bash
pytest -q
```

## API 예시

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/screenshot.png"
```
