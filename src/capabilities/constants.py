"""
MCP Capabilities Constants
공통 상수 및 설정값들을 정의 (외부 의존성 최소화)
"""

# MCP Protocol Constants (안정적인 프로토콜 관련 상수만)
MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SESSION_ID_HEADER = "mcp-session-id"
MCP_SSO_ID_HEADER = "X-SSO-ID"
MCP_API_KEY_HEADER = "X-API-Key"

# Default Values (시스템 기본값)
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_TOP_K = 5
DEFAULT_MAX_RESULTS = 10

# Log Tags (로깅 관련)
MCP_SERVICE_TAG = "[MCP_SERVICE]"
MCP_CLIENT_TAG = "[MCP_CLIENT]"
REGISTRY_TAG = "[REGISTRY]"

# Error Messages (시스템 에러 메시지)
INITIALIZATION_FAILED = "MCP 서비스 초기화 실패"
TOOL_LIST_FAILED = "도구 목록 조회 실패"
TOOL_EXECUTION_FAILED = "도구 실행 실패"
CLIENT_NOT_FOUND = "MCP 클라이언트를 찾을 수 없습니다"
REGISTRY_FILE_NOT_FOUND = "레지스트리 파일이 존재하지 않습니다"
SCOPE_UPDATE_FAILED = "scope 업데이트 실패"
