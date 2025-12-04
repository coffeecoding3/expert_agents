"""
MCP Capabilities Exceptions
MCP 관련 예외 클래스들을 정의
"""


class MCPError(Exception):
    """MCP 기본 예외 클래스"""
    pass


class MCPInitializationError(MCPError):
    """MCP 초기화 관련 예외"""
    pass


class MCPClientError(MCPError):
    """MCP 클라이언트 관련 예외"""
    pass


class MCPToolError(MCPError):
    """MCP 도구 실행 관련 예외"""
    pass


class MCPRegistryError(MCPError):
    """MCP 레지스트리 관련 예외"""
    pass


class MCPAuthenticationError(MCPError):
    """MCP 인증 관련 예외"""
    pass


class MCPNetworkError(MCPError):
    """MCP 네트워크 관련 예외"""
    pass
