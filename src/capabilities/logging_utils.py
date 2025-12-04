"""
MCP Logging Utilities
공통 로깅 기능을 제공하는 유틸리티
"""

import logging
from typing import Any, Dict, Optional

from .constants import MCP_CLIENT_TAG, MCP_SERVICE_TAG, REGISTRY_TAG

logger = logging.getLogger(__name__)


class MCPLogger:
    """MCP 전용 로거 클래스"""

    @staticmethod
    def _format_message(tag: str, message: str, **kwargs) -> str:
        """메시지 포맷팅"""
        if kwargs:
            message += f" - {kwargs}"
        return f"{tag} {message}"

    @staticmethod
    def debug(tag: str, message: str, **kwargs):
        """디버그 로그 출력"""
        formatted_message = MCPLogger._format_message(tag, message, **kwargs)
        logger.debug(formatted_message)

    @staticmethod
    def info(tag: str, message: str, **kwargs):
        """정보 로그 출력"""
        formatted_message = MCPLogger._format_message(tag, message, **kwargs)
        logger.info(formatted_message)

    @staticmethod
    def warning(tag: str, message: str, **kwargs):
        """경고 로그 출력"""
        formatted_message = MCPLogger._format_message(tag, message, **kwargs)
        logger.warning(formatted_message)

    @staticmethod
    def error(tag: str, message: str, **kwargs):
        """에러 로그 출력"""
        formatted_message = MCPLogger._format_message(tag, message, **kwargs)
        logger.error(formatted_message)


class ServiceLogger:
    """MCP 서비스 전용 로거"""

    @staticmethod
    def debug(message: str, **kwargs):
        MCPLogger.debug(MCP_SERVICE_TAG, message, **kwargs)

    @staticmethod
    def info(message: str, **kwargs):
        MCPLogger.info(MCP_SERVICE_TAG, message, **kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        MCPLogger.warning(MCP_SERVICE_TAG, message, **kwargs)

    @staticmethod
    def error(message: str, **kwargs):
        MCPLogger.error(MCP_SERVICE_TAG, message, **kwargs)


class ClientLogger:
    """MCP 클라이언트 전용 로거"""

    @staticmethod
    def debug(message: str, **kwargs):
        MCPLogger.debug(MCP_CLIENT_TAG, message, **kwargs)

    @staticmethod
    def info(message: str, **kwargs):
        MCPLogger.info(MCP_CLIENT_TAG, message, **kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        MCPLogger.warning(MCP_CLIENT_TAG, message, **kwargs)

    @staticmethod
    def error(message: str, **kwargs):
        MCPLogger.error(MCP_CLIENT_TAG, message, **kwargs)


class RegistryLogger:
    """MCP 레지스트리 전용 로거"""

    @staticmethod
    def debug(message: str, **kwargs):
        MCPLogger.debug(REGISTRY_TAG, message, **kwargs)

    @staticmethod
    def info(message: str, **kwargs):
        MCPLogger.info(REGISTRY_TAG, message, **kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        MCPLogger.warning(REGISTRY_TAG, message, **kwargs)

    @staticmethod
    def error(message: str, **kwargs):
        MCPLogger.error(REGISTRY_TAG, message, **kwargs)
