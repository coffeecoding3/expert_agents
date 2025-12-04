"""
Capabilities Layer Package

MCP 서버 및 외부 서비스 연결을 통한 AI 에이전트 능력 확장
"""

from .mcp_service import mcp_service
from .registry_manager import registry_manager
from .exceptions import (
    MCPError,
    MCPInitializationError,
    MCPClientError,
    MCPToolError,
    MCPRegistryError,
    MCPAuthenticationError,
    MCPNetworkError
)

__version__ = "0.1.0"

__all__ = [
    "mcp_service",
    "registry_manager",
    "MCPError",
    "MCPInitializationError", 
    "MCPClientError",
    "MCPToolError",
    "MCPRegistryError",
    "MCPAuthenticationError",
    "MCPNetworkError"
]
