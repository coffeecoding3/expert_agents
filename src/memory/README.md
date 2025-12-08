# Memory Schema and Storage Guide

이 문서는 CAIA의 메모리 구조, 필드 의미, 저장 위치(mysql/redis), 조회 방법을 한눈에 정리합니다.

## 공통 필드 정의

- memory_type
  - 표준: `semantic` | `episodic` | `procedural`
- category(자유롭게 저장 가능)
  - personal 분류 태그 (예: `identity`, `preference`, `interest`, `constraint`, `project`, `contact`, `domain`)
- importance
  - 중요도(기본 1.0). 현재 저장 시 전달값 그대로 사용; 자동 재계산 로직 없음
  - MySQL 정리(cleanup) 시 낮은 중요도(<0.5) 오래된 항목 우선 삭제에 활용

---

## STM (Short-Term Memory, 세션 휘발성 메모리)

- 저장소: Redis (리스트 구조)
- 키 스키마:
  - 세션 미지정(누적): `mem:{user_id}:{date}:unknown_{uuid}`
  - 세션 지정: `mem:{user_id}:{date}:{session_id}`
- 항목 구조(JSON):
```json
{
  "id": 12345,
  "user_id": 1,
  "agent_id": 1,
  "content": "User: ...\nAI: ...",
  "memory_type": "messages" | "summary",
  "importance": 1.0,
  "category": null,
  "session_id": "sessA",
  "created_timestamp": 1703123456
}
```
- 쓰기 API (in code):
  - `memory_manager.save_stm_message(user_id, content, agent_id, session_id=None)`
  - `memory_manager.save_stm_summary(user_id, summary, agent_id, session_id=None)`
- 읽기 API:
  - `memory_manager.get_stm_recent_messages(user_id, agent_id, k=5, session_id=None)`
  - `memory_manager.get_stm_summary(user_id, agent_id, session_id=None)`
- 특징:
  - TTL 미설정(영구 보관). 필요 시 Redis 정책/코드 수정으로 만료 설정 가능
  - 세션 구분 지원(session_id)

---

## LTM (Long-Term Memory, DB저장 메모리)

- 저장소: MySQL (`memories` 테이블)
- 주요 컬럼(요지):
  - `id` (PK), `agent_id`, `user_id`
  - `content` (TEXT, json? 고민중)
  - `memory_type` (`semantic` | `episodic` | `procedural`)
  - `importance` (FLOAT)
  - `category` (VARCHAR)
  - `created_at`, `updated_at`, `accessed_at` (TIMESTAMP)
- 쓰기 API:
  - `memory_manager.save_ltm(user_id, content, categories=None, agent_id=None, importance=1.0)`
    - `categories`가 여러 개면 레코드를 카테고리별로 개별 저장
- 읽기/검색 API:
  - `memory_manager.search_memories(user_id, agent_id, limit=10, threshold=0.8)`
  - `memory_manager.get_recent_memories(user_id, agent_id, limit=5)`
- 정리/관리:
  - `memory_manager.cleanup_old_memories(days=30)`
    - `created_at < NOW()-days` && `importance < 0.5` 인 항목 삭제

---

## 환경 변수

- `DATABASE_URL` (MySQL): `mysql://user:password@host:3306/database`
- `REDIS_URL`: `redis://:password@host:6379/0`
- 선택: `MEMORY_PROVIDER` = `mysql` (기본), Redis는 STM으로 자동 초기화

---

## 고도화

- 중요도(importance) 자동 산정이 필요하면 저장 훅에 규칙/LLM 기반 평가를 추가하여 보정할 수 있습니다.
