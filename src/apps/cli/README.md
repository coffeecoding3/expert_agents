# Expert Agents CLI 사용법

간단히 설치하고, 세션 단위 채팅과 STM(Short-Term Memory) 확인을 CLI로 테스트할 수 있습니다.

## 설치

```bash
pip install -e .
```

설치 후 제공 명령:
- expert-agents (CLI)
- expert-agents-api (FastAPI 앱 엔트리)

## 기본 사용

- 단순 응답(비스트리밍)
```bash
expert-agents chat -q "질문 내용" -u 1
```

- 스트리밍 응답(SSE)
```bash
expert-agents chat -q "질문 내용" -u 1 --stream
```

- 호스트 변경(로컬 API가 다른 포트/호스트인 경우)
```bash
expert-agents chat -q "질문" -u 1 --host http://localhost:8000 --stream
```

## 세션 유지(세션별 STM 저장)

세션 ID를 지정하면 Redis STM이 `mem:{agent_id}:{user_id}:{session_id}` 키로 분리 저장됩니다.

- 세션 A 시작
```bash
expert-agents chat -q "세션 A 첫 메시지" -u 1 -s sessA --stream
```

- 같은 세션 A로 후속 질문
```bash
expert-agents chat -q "세션 A 두번째" -u 1 -s sessA --stream
```

- 다른 세션 B로 분리
```bash
expert-agents chat -q "세션 B 첫 메시지" -u 1 -s sessB --stream
```

## STM(단기 메모리) 조회

최근 STM 메시지와 세션 요약을 CLI로 확인할 수 있습니다.

- 특정 세션 조회(예: user 1, agent 1, session sessA, 최근 10개)
```bash
expert-agents stm -u 1 -a 1 -s sessA -k 10
```

- 세션 미지정(누적 키 `mem:{agent_id}:{user_id}`) 조회
```bash
expert-agents stm -u 1 -a 1 -k 10
```

출력 예시:
```
STM Summary: N/A
Recent (2):
  1. [stm_message] session=sessA id=123 -> User: …\nAI: …
  2. [stm_message] session=sessA id=124 -> User: …\nAI: …
```

## 환경 변수

- Redis(컨테이너 기준) 비밀번호가 설정되어 있으므로 API 컨테이너에는 다음이 설정되어야 합니다:
```
REDIS_URL=redis://:password@redis:6379/0
```

## 트러블슈팅

- `DATABASE_URL이 설정되지 않았습니다. 메모리 기능이 제한됩니다.` 경고가 보이면 장기/개인 메모리(MySQL)가 비활성입니다. STM만 사용 중일 수 있습니다.
- 세션 STM이 보이지 않으면 먼저 채팅이 정상 완료되었는지(저장 로그 `ok=True`)와 Redis 접속/인증 설정을 확인하세요.
