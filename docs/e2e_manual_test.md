# /upload 통합 파이프라인 E2E 수동 테스트 절차

아래 절차는 `/upload` 엔드포인트의 전체 파이프라인(해시/저장 → Gemini 추출 → 정규화/카테고리/expiry_estimated 생성 → Google Sheets append)을 검증합니다.

## 1) 사전 준비

1. 환경변수 설정
   - `GEMINI_API_KEY`
   - `SPREADSHEET_ID` (또는 `GOOGLE_SHEET_ID`)
   - `GOOGLE_CREDENTIALS_JSON`
   - `SHEET_NAME` (옵션, 기본 `Fridge`)
2. 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

3. 테스트 이미지 준비
   - `tests/assets/fridge_case_01.jpg` (신규 업로드용)
   - `tests/assets/fridge_case_01_dup.jpg` (동일 이미지 복제본, 중복 검사용)
   - `tests/assets/invalid.txt` (형식 오류 검사용)

---

## 2) 정상 신규 업로드 검증

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -F "file=@tests/assets/fridge_case_01.jpg;type=image/jpeg"
```

### 기대 결과
- HTTP 200
- `duplicate: false`
- `num_items_extracted >= 1`
- `num_rows_appended >= 1`
- `sheet.spreadsheet_id`, `sheet.sheet_name` 존재
- `items_preview` 최대 5개
- `processing_seconds` 존재

### 기록 템플릿
- 응답 JSON 붙여넣기:

```json
{
  "duplicate": false,
  "num_items_extracted": 0,
  "num_rows_appended": 0,
  "sheet": {"spreadsheet_id": "", "sheet_name": ""},
  "items_preview": [],
  "processing_seconds": 0.0
}
```

---

## 3) 중복 업로드 검증

> 같은 이미지를 다시 업로드하거나 동일한 복제본 파일(`fridge_case_01_dup.jpg`) 사용

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -F "file=@tests/assets/fridge_case_01_dup.jpg;type=image/jpeg"
```

### 기대 결과
- HTTP 200
- `duplicate: true`
- `num_items_extracted: 0`
- `num_rows_appended: 0`
- `items_preview: []`
- `processing_seconds` 존재

### 기록 템플릿
- 응답 JSON 붙여넣기:

```json
{
  "duplicate": true,
  "num_items_extracted": 0,
  "num_rows_appended": 0,
  "sheet": {"spreadsheet_id": "", "sheet_name": ""},
  "items_preview": [],
  "processing_seconds": 0.0
}
```

---

## 4) 입력 검증 실패(stage 확인)

### 4-1) 지원하지 않는 MIME

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -H "accept: application/json" \
  -F "file=@tests/assets/invalid.txt;type=text/plain"
```

### 기대 결과
- HTTP 400
- 응답에 `stage: "validate_input"`
- 응답에 `processing_seconds` 존재

### 기록 템플릿

```json
{
  "stage": "validate_input",
  "message": "Only JPG and PNG files are supported",
  "processing_seconds": 0.0
}
```

---

## 5) 시트 반영 검증

1. Google Sheets의 `SHEET_NAME` 시트 확인
2. 신규 업로드 시 다음 컬럼이 채워졌는지 확인
   - `name_raw`, `name_norm`, `qty`, `unit`, `storage`, `category`, `default_days`, `expiry_estimated`, `source_hash`
3. 중복 업로드 후에는 행 수가 증가하지 않았는지 확인

### 기록 템플릿
- 신규 업로드 전/후 행 수:
- 중복 업로드 후 행 수:
- 샘플 행 값(텍스트):

---

## 6) 로그 타이밍 검증

서버 로그에서 단계별 타이밍 로그를 확인합니다.

- `[stage=validate_input] done in ...s`
- `[stage=hash_and_save] done in ...s`
- `[stage=gemini_extract] done in ...s`
- `[stage=normalize_items] done in ...s`
- `[stage=append_sheet] done in ...s`

### 기록 템플릿
- 로그 스니펫 붙여넣기:

```text
(여기에 실제 로그를 붙여넣으세요)
```

---

## 7) 실패 케이스(stage) 검증 체크리스트

- [ ] Gemini API 오류 시 `stage=gemini_extract`로 반환
- [ ] Sheets append 오류 시 `stage=append_sheet`로 반환
- [ ] 기타 예외 시 `stage=unknown`로 반환

