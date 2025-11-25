# LexAI API 문서

LexAI는 법령 개정 분석 및 사내 규정 변경 조언을 제공하는 API입니다.

## 목차

- [API 개요](#api-개요)
- [1. 법령 개정 분석 API](#1-법령-개정-분석-api)
- [2. 정합성 체크 조회 API](#2-정합성-체크-조회-api)
- [에러 처리](#에러-처리)

---

## API 개요

### Base URL
```
http://localhost:8000/lexai/api/v1
```

### 공통 정보
- **인증**: 현재 인증 불필요
- **Content-Type**: `application/json`
- **응답 형식**: JSON

---

## 1. 법령 개정 분석 API

법령 개정 내용을 분석하여 사내 규정 변경 조언을 생성합니다.

### 엔드포인트
```
POST /lexai/api/v1/analyze
```

### 요청 (Request)

#### Request Body
```json
{
  "openapi_log_id": "55",
  "old_and_new_no": "273603",
  "law_nm": "산업안전보건기준에 관한 규칙",
  "contents": [
    {
      "content_no": "1",
      "old_content": "제241조(화재위험작업 시의 준수사항) ① (생 략)",
      "new_content": "제241조(화재위험작업 시의 준수사항) ① (현행과 같음)"
    },
    {
      "content_no": "2",
      "old_content": "② 사업주는 가연성물질이 있는 장소에서 화재위험작업을 하는 경우에는\n화재예방에 필요한 다음 각 호의 사항을 준수하여야 한다.",
      "new_content": "② 사업주는 가연성물질이 있는 장소에서 화재위험작업을 하는 경우에\n는 화재예방에 필요한 다음 각 호의 사항을 준수하여야 한다."
    },
    {
      "content_no": "4",
      "old_content": "4. 용접불티 비산방지덮개, 용접방화포 등 불꽃, 불티 등 비산방지조치 <P>\n<후단 신설></P>",
      "new_content": "4. 용접불티 비산방지덮개, 용접방화포 등 불꽃, 불티 등 비산방지조치.\n<P>이 경우 용접방화포는 「소방시설 설치 및 관리에 관한 법률」 제40조제1항에 따라 성능인증을 받\n은 것을 사용해야 한다.</P>"
    }
  ]
}
```

#### 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `openapi_log_id` | string | ✅ | OpenAPI 로그 ID |
| `old_and_new_no` | string | ✅ | 개정 전후 번호 |
| `law_nm` | string | ✅ | 법령명 |
| `contents` | array | ✅ | 법령 개정 내용 목록 |
| `contents[].content_no` | string | ✅ | 내용 번호 |
| `contents[].old_content` | string | ✅ | 개정 전 내용 |
| `contents[].new_content` | string | ✅ | 개정 후 내용 |

### 응답 (Response)

#### 성공 응답 (200 OK)
```json
{
  "openapi_log_id": "55",
  "old_and_new_no": "273603",
  "details": [
    {
      "center": "안전환경센터",
      "category": "안전",
      "standard": "안전보건관리규정",
      "content_no": "4",
      "before_lgss_content": "N/A",
      "ai_review": "용접방화포는 「소방시설 설치 및 관리에 관한 법률」 제40조제1항에 따라 성능인증을 받은 것을 사용 규정 추가",
      "ai_suggestion": "비산방지조치에 성능인증 항목 추가",
      "suggetsion_accuracy": "80"
    }
  ],
  "corporate_knowledge": {
    "documents": [
      {
        "title": "안전보건관리규정",
        "content": "..."
      }
    ]
  }
}
```

#### 응답 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `openapi_log_id` | string | OpenAPI 로그 ID |
| `old_and_new_no` | string | 개정 전후 번호 |
| `details` | array | 규정 변경 상세 목록 |
| `details[].center` | string | 센터명 (예: 안전환경센터, 안전보건센터) |
| `details[].category` | string | 카테고리 (예: 안전, 환경, 보건) |
| `details[].standard` | string | 규정명 (예: 안전보건관리규정) |
| `details[].content_no` | string | 법령 개정 내용 번호 |
| `details[].before_lgss_content` | string | 변경 전 LGSS 내용 |
| `details[].ai_review` | string | AI 검토 내용 |
| `details[].ai_suggestion` | string | AI 제안 사항 |
| `details[].suggetsion_accuracy` | string | 제안 정확도 (0-100) |
| `corporate_knowledge` | object | 검색된 사내지식 정보 (Optional) |
| `corporate_knowledge.documents` | array | 검색된 문서 목록 |

### 사용 예시

#### cURL
```bash
curl -X POST "http://localhost:8000/lexai/api/v1/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "openapi_log_id": "55",
    "old_and_new_no": "273603",
    "law_nm": "산업안전보건기준에 관한 규칙",
    "contents": [
      {
        "content_no": "1",
        "old_content": "제241조(화재위험작업 시의 준수사항) ① (생 략)",
        "new_content": "제241조(화재위험작업 시의 준수사항) ① (현행과 같음)"
      }
    ]
  }'
```

#### Python (httpx)
```python
import httpx
import asyncio

async def analyze_law_revision():
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            "http://localhost:8000/lexai/api/v1/analyze",
            json={
                "openapi_log_id": "55",
                "old_and_new_no": "273603",
                "law_nm": "산업안전보건기준에 관한 규칙",
                "contents": [
                    {
                        "content_no": "1",
                        "old_content": "제241조(화재위험작업 시의 준수사항) ① (생 략)",
                        "new_content": "제241조(화재위험작업 시의 준수사항) ① (현행과 같음)"
                    }
                ]
            }
        )
        return response.json()

result = asyncio.run(analyze_law_revision())
print(result)
```

### 처리 흐름

1. **검색 쿼리 생성**: 법령명과 개정 내용을 분석하여 사내 규정 검색 쿼리 생성
2. **사내지식 검색**: 생성된 쿼리로 사내 규정 검색
3. **조언 생성**: 법령 개정 내용과 사내지식을 기반으로 LLM이 규정 변경 조언 생성
4. **결과 저장**: 분석 결과를 데이터베이스에 저장
5. **응답 반환**: 생성된 조언을 JSON 형식으로 반환

### 주의사항

- 처리 시간이 오래 걸릴 수 있습니다 (최대 300초)
- `corporate_knowledge`는 사내지식 검색 결과가 있을 때만 포함됩니다
- `details` 배열이 비어있으면 수정제안이 없다는 의미입니다

---

## 2. 정합성 체크 조회 API

작업 완료된 법령 개정 분석 결과를 조회하여 정합성 체크 결과를 반환합니다.

### 엔드포인트
```
POST /lexai/api/v1/consistency-check
```

### 요청 (Request)

#### Request Body
```json
{
  "law_nm": "산업안전보건기준에 관한 규칙",
  "standard": "안전보건관리규정"
}
```

#### 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `law_nm` | string | ✅ | 법령명 |
| `standard` | string | ✅ | 규정명 |

### 응답 (Response)

#### 성공 응답 (200 OK)
```json
{
  "law_nm": "산업안전보건기준에 관한 규칙",
  "standard": "안전보건관리규정",
  "check_rst": "일부 수정",
  "suggetsion_accuracy": "88",
  "ai_suggestions": [
    {
      "line": "4",
      "suggestion": "비산방지조치에 성능인증 항목 추가"
    },
    {
      "line": "8",
      "suggestion": "'운반기계등'을 '굴착기계등'으로 수정"
    }
  ]
}
```

#### 응답 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `law_nm` | string | 법령명 |
| `standard` | string | 규정명 |
| `check_rst` | string | 체크 결과 ("완료" 또는 "일부 수정") |
| `suggetsion_accuracy` | string | 제안 정확도 (0-100) |
| `ai_suggestions` | array | AI 제안 사항 목록 |
| `ai_suggestions[].line` | string | 라인 번호 (법령 개정 내용 번호) |
| `ai_suggestions[].suggestion` | string | 제안 내용 |

### 사용 예시

#### cURL
```bash
curl -X POST "http://localhost:8000/lexai/api/v1/consistency-check" \
  -H "Content-Type: application/json" \
  -d '{
    "law_nm": "산업안전보건기준에 관한 규칙",
    "standard": "안전보건관리규정"
  }'
```

#### Python (httpx)
```python
import httpx
import asyncio

async def get_consistency_check():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/lexai/api/v1/consistency-check",
            json={
                "law_nm": "산업안전보건기준에 관한 규칙",
                "standard": "안전보건관리규정"
            }
        )
        return response.json()

result = asyncio.run(get_consistency_check())
print(result)
```

### 동작 방식

1. **작업 조회**: `law_nm`으로 가장 최근 완료된 분석 작업을 조회
2. **규정 매칭**: `advice_parsed`에서 `standard`가 일치하는 detail을 찾음
3. **결과 변환**: 찾은 detail을 `ConsistencyCheckResponse` 형식으로 변환
   - `check_rst`: 제안이 있으면 "일부 수정", 없으면 "완료"
   - `suggetsion_accuracy`: 매칭된 detail들의 정확도 평균
   - `ai_suggestions`: `content_no`를 `line`으로, `ai_suggestion`을 `suggestion`으로 매핑

### 주의사항

- 해당 법령명으로 완료된 분석 작업이 없으면 404 에러가 발생합니다
- 해당 규정명에 대한 분석 결과가 없으면 404 에러가 발생합니다
- `ai_suggestions`가 비어있으면 수정제안이 없다는 의미입니다

---

## 에러 처리

### 공통 에러 응답

#### 404 Not Found
```json
{
  "detail": "에이전트를 찾을 수 없습니다."
}
```

#### 500 Internal Server Error
```json
{
  "detail": "법령 개정 분석 중 오류가 발생했습니다: [에러 메시지]"
}
```

### API별 특정 에러

#### 1. 법령 개정 분석 API

**404 Not Found**
- 에이전트를 찾을 수 없을 때

**500 Internal Server Error**
- LLM 호출 실패
- 데이터베이스 오류
- 기타 서버 내부 오류

#### 2. 정합성 체크 조회 API

**404 Not Found**
- 해당 법령명으로 완료된 분석 결과를 찾을 수 없을 때
- 분석 결과 데이터가 없을 때
- 해당 규정명에 대한 분석 결과를 찾을 수 없을 때

**500 Internal Server Error**
- 데이터베이스 오류
- 기타 서버 내부 오류

---

## 테스트

테스트 스크립트는 `tests/test_lexai_api.py`에 있습니다.

### 실행 방법
```bash
# Python httpx로 테스트
python tests/test_lexai_api.py

# curl 명령어 출력
python tests/test_lexai_api.py curl
```

---

## 참고사항

- 모든 API는 비동기로 처리됩니다
- 분석 작업은 데이터베이스에 저장되며, 이후 조회가 가능합니다
- `corporate_knowledge`는 사내지식 검색 결과를 포함합니다
- 정확도 점수는 0-100 사이의 값입니다

