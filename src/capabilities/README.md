# MCP (Model Context Protocol) Capabilities

이 디렉토리는 MCP(Model Context Protocol)를 통해 외부 서비스와 통신하여 다양한 도구들을 사용할 수 있도록 하는 기능들을 제공합니다.

## 📁 구조

```
src/capabilities/
├── __init__.py                 # 패키지 초기화
├── constants.py                # 공통 상수 정의
├── exceptions.py               # 예외 클래스 정의
├── logging_utils.py            # 로깅 유틸리티
├── tool_schemas.py             # 도구 스키마 관리
├── mcp_service.py              # MCP 서비스 메인 클래스
├── registry_manager.py         # MCP 서버 레지스트리 관리
├── registry.yaml               # MCP 서버 설정 파일
├── servers/                   # MCP 서버 관련 모듈
│   ├── external/              # 외부 MCP 서버 클라이언트
│   │   ├── __init__.py        # 외부 서버 초기화
│   │   ├── mcp_client.py      # MCP 클라이언트 구현
│   │   └── client_manager.py   # 클라이언트 매니저
│   └── internal/              # 내부 MCP 서버 (추후 추가 예정)
└── README.md                   # 이 파일
```

## 주요 컴포넌트

### 1. MCPService (`mcp_service.py`)
MCP 클라이언트들을 초기화하고 관리하는 메인 서비스 클래스입니다.

**주요 기능:**
- MCP 서비스 초기화
- 사용 가능한 도구 목록 조회
- 도구 실행
- 사내지식 검색 도구 실행 (특별 메서드)
- 스키마 검증과 함께 도구 실행

### 2. MCPClient (`servers/external/mcp_client.py`)
외부 MCP 서버와 통신하는 클라이언트 클래스입니다.

**주요 기능:**
- HTTP 기반 MCP 서버 통신
- 도구 목록 조회
- 도구 실행
- 인증 및 재시도 로직
- SSE 응답 파싱

### 3. MCPClientManager (`servers/external/client_manager.py`)
MCP 클라이언트들을 관리하는 매니저 클래스입니다.

**주요 기능:**
- 클라이언트 초기화 및 관리
- 도구 실행 위임
- 모든 클라이언트의 도구 목록 조회
- 리소스 정리

### 4. MCPRegistryManager (`registry_manager.py`)
MCP 서버 레지스트리를 동적으로 관리하는 매니저입니다.

**주요 기능:**
- 레지스트리 파일 로드/저장
- 클라이언트 scope 동적 업데이트
- 클라이언트 설정 관리

### 5. 공통 유틸리티
- **`constants.py`**: 모든 상수 정의 (타임아웃, 재시도 횟수, 도구 이름 등)
- **`exceptions.py`**: MCP 관련 예외 클래스들
- **`logging_utils.py`**: 통합 로깅 유틸리티
- **`tool_schemas.py`**: 도구 스키마 관리

## 🚀 사용 방법

### 기본 초기화

```python
from src.capabilities.mcp_service import mcp_service

# MCP 서비스 초기화
await mcp_service.initialize()

# 사용 가능한 도구 목록 조회
tools = await mcp_service.get_available_tools()
print(f"사용 가능한 도구: {len(tools)}개")
```

### 일반적인 도구 호출

```python
# 특정 클라이언트의 도구 실행
result = await mcp_service.call_tool(
    client_name="lgenie",
    tool_name="retrieve_coporate_knowledge",
    arguments={
        "query": "프로젝트 진행상황",
        "system_codes": ["custom_system1", "custom_system2"],
        "top_k": 10
    },
    sso_id="user123"
)
```

## 🎯 사내지식 검색 도구 (Corporate Knowledge Tool)

가장 자주 사용되는 사내지식 검색 기능을 위한 특별한 메서드가 제공됩니다.

### 기본 사용법

```python
from src.capabilities.mcp_service import mcp_service

# 사내지식 검색 실행
result = await mcp_service.call_corporate_knowledge_tool(
    query="프로젝트 진행상황",
    system_codes=["custom_system1", "custom_system2"],  # 커스텀 시스템 코드
    top_k=10,
    sso_id="user123"
)
```

### 매개변수 설명

- **`query`** (str): 검색할 질의어
- **`system_codes`** (List[str], optional): 검색할 시스템 코드 목록
  - 기본값: `ConfigUtils.get_default_system_codes()`에서 가져옴
- **`top_k`** (int, optional): 반환할 결과 개수 (기본값: 5)
- **`sso_id`** (str, optional): 사용자 SSO ID

### 실제 사용 예시

```python
# 예시
result = await mcp_service.call_corporate_knowledge_tool(
    query="프로젝트 진행상황",
    system_codes=["custom_system1", "custom_system2"],
    top_k=10,
    sso_id="hq15"
)
```

## 설정 파일

### registry.yaml
MCP 서버 설정을 관리하는 YAML 파일입니다.

```yaml
global:
  rate_limit: 100
  retry_attempts: 3
  timeout: 30
servers:
  external:
    lgenie-mcp:
      description: LGenie MCP server
      endpoint: ${LGENIE_ENDPOINT:-}/lgenie-mcp/mcp
      headers:
        X-API-Key: ${LGENIE_MCP_API_KEY:-}
        mcp-session-id: ''
        X-SSO-ID: ''
      lgenie: true
      scope: []
      status: active
      transport: http
  internal:
    llm-knowledge:
      description: 추후 추가 예정
      endpoint: ''
      scope: []
      transport: stdio
```

## 지원되는 도구들

현재 지원되는 주요 도구들:

1. **`retrieve_coporate_knowledge`** - 사내지식 검색
2. **`retrieve_personal_knowledge`** - 개인지식 검색
3. **`get_events`** - 이벤트 조회
4. **`get_mails`** - 메일 조회
5. **`send_mail`** - 메일 발송
6. **`get_employee_infos_from_human_question`** - 직원 정보 조회
7. **`get_olap_search_data`** - OLAP 데이터 검색
8. **`retrieve_scm_knowledge`** - SCM 지식 검색
9. **`get_web_search_data`** - 웹 검색 데이터

### 스키마 검증과 함께 도구 실행

```python
# 스키마 검증과 함께 도구 실행(스키마 변경 체크)
result = await mcp_service.call_mcp_tool_with_validation(
    tool_name="retrieve_coporate_knowledge",
    client_name="lgenie",
    args={
        "query": "프로젝트 진행상황",
        "system_codes": ["custom_system1"],
        "top_k": 5
    },
    sso_id="user123"
)
```

### 클라이언트 scope 조회

```python
# 특정 클라이언트의 도구 목록 조회
scope = mcp_service.get_client_scope("lgenie")
print(f"lgenie 클라이언트 도구: {scope}")
```

## 🔧 환경 변수

다음 환경 변수들이 필요합니다:

- `LGENIE_ENDPOINT`: LGenie MCP 서버 엔드포인트
- `LGENIE_MCP_API_KEY`: LGenie MCP API 키

## 📝 로깅

MCP 관련 모든 작업은 상세한 로깅을 제공합니다:

- **DEBUG**: 상세한 디버깅 정보
- **INFO**: 일반적인 작업 정보
- **WARNING**: 경고 메시지
- **ERROR**: 오류 메시지

로그는 `[MCP_SERVICE]`, `[MCP_CLIENT]`, `[REGISTRY]` 등의 태그로 구분됩니다.

### 로깅 유틸리티 사용법

```python
from src.capabilities.logging_utils import ServiceLogger, ClientLogger, RegistryLogger

# 서비스 로깅
ServiceLogger.info("MCP 서비스 초기화 완료")
ServiceLogger.error("초기화 실패", error=str(e))

# 클라이언트 로깅
ClientLogger.debug("HTTP 요청 시작", endpoint=endpoint)
ClientLogger.warning("재시도 중", attempt=2)

# 레지스트리 로깅
RegistryLogger.info("레지스트리 업데이트 완료", client_count=5)
```

## 🚨 오류 처리

MCP 서비스는 다음과 같은 오류 상황을 처리합니다:

1. **인증 오류**: 자동 재시도 및 브라우저 리다이렉트
2. **네트워크 오류**: 설정된 횟수만큼 재시도
3. **서버 오류**: 적절한 오류 메시지 반환
4. **초기화 실패**: 서비스 사용 불가 상태로 전환

### 예외 클래스

```python
from src.capabilities.exceptions import (
    MCPError,                    # 기본 MCP 예외
    MCPInitializationError,      # 초기화 관련 예외
    MCPClientError,             # 클라이언트 관련 예외
    MCPToolError,               # 도구 실행 관련 예외
    MCPRegistryError,           # 레지스트리 관련 예외
    MCPAuthenticationError,     # 인증 관련 예외
    MCPNetworkError            # 네트워크 관련 예외
)

# 예외 처리 예시
try:
    await mcp_service.initialize()
except MCPInitializationError as e:
    print(f"초기화 실패: {e}")
except MCPNetworkError as e:
    print(f"네트워크 오류: {e}")
```

## 🔄 리소스 관리

```python
# 서비스 종료 (리소스 정리)
await mcp_service.close()
```

MCP 서비스는 비동기 컨텍스트 매니저를 지원하여 자동으로 리소스를 정리합니다.

## 개발 가이드

### 도구 스키마 관리


```python
from src.capabilities.tool_schemas import ToolSchemaManager

# 도구 스키마 조회
schema = ToolSchemaManager.get_tool_schema("retrieve_coporate_knowledge")
print(schema)

# 모든 도구 이름 조회
tool_names = ToolSchemaManager.get_all_tool_names()
print(f"사용 가능한 도구: {tool_names}")
```

### 레지스트리 관리

```python
from src.capabilities.registry_manager import registry_manager

# 레지스트리 로드
registry_data = registry_manager.load_registry()

# 클라이언트 설정 조회
config = registry_manager.get_client_config("lgenie")

# 모든 클라이언트 설정 조회
all_configs = registry_manager.get_all_client_configs()
```
