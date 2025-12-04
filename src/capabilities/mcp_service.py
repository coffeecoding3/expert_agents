"""
MCP Service
MCP 클라이언트들을 초기화하고 관리하는 서비스
"""

from typing import Any, Dict, List, Optional

from configs.app_config import load_config
from src.capabilities.servers.external.client_manager import mcp_manager
from src.capabilities.logging_utils import ServiceLogger
from src.capabilities.exceptions import MCPInitializationError, MCPToolError
from src.capabilities.constants import (
    DEFAULT_TOP_K,
    INITIALIZATION_FAILED,
    TOOL_LIST_FAILED,
    TOOL_EXECUTION_FAILED,
    CLIENT_NOT_FOUND,
)
from src.schemas.raih_exceptions import (
    RAIHBusinessException,
    RAIHAuthorizationException,
)


class MCPService:
    """MCP 서비스 - MCP 클라이언트들을 초기화하고 관리"""

    def __init__(self):
        self.initialized = False
        self.config: Optional[Dict[str, Any]] = None

    async def _ensure_initialized(self) -> None:
        """서비스가 초기화되지 않았으면 초기화"""
        if not self.initialized:
            await self.initialize()

    async def initialize(self) -> bool:
        """MCP 서비스 초기화"""
        if self.initialized:
            ServiceLogger.debug("이미 초기화됨")
            return True

        try:
            self.config = load_config()
            await mcp_manager.initialize_from_config(self.config)
            self.initialized = True
            return True
        except Exception as e:
            ServiceLogger.error(f"{INITIALIZATION_FAILED}: {e}")
            raise MCPInitializationError(f"{INITIALIZATION_FAILED}: {e}") from e

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """사용 가능한 MCP 도구 목록 반환"""
        await self._ensure_initialized()

        try:
            # ServiceLogger.debug("도구 목록 조회 시작")
            tools = await mcp_manager.get_all_tools()
            # ServiceLogger.debug(f"도구 목록 조회 완료: {len(tools)}개")
            return tools
        except Exception as e:
            ServiceLogger.error(f"{TOOL_LIST_FAILED}: {e}")
            raise MCPToolError(f"{TOOL_LIST_FAILED}: {e}") from e

    async def call_tool(
        self,
        client_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        sso_id: Optional[str] = None,
    ) -> Any:
        """MCP 도구 실행"""
        await self._ensure_initialized()

        try:
            result = await mcp_manager.call_tool(
                client_name, tool_name, arguments, sso_id
            )
            return result

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            raise e

        except Exception as e:
            ServiceLogger.error(f"{TOOL_EXECUTION_FAILED} - {tool_name}: {e}")
            raise MCPToolError(f"{TOOL_EXECUTION_FAILED} - {tool_name}: {e}") from e

    def get_client_scope(self, client_name: str) -> List[str]:
        """클라이언트의 도구 이름 목록 반환 (scope용)"""
        try:
            scope = mcp_manager.get_client_scope(client_name)
            ServiceLogger.debug(
                f"클라이언트 scope 조회: {client_name} - {len(scope)}개 도구"
            )
            return scope
        except Exception as e:
            ServiceLogger.error(f"클라이언트 scope 조회 실패 - {client_name}: {e}")
            return []

    async def call_corporate_knowledge_tool(
        self,
        query: str,
        sso_id: Optional[str] = None,
        system_codes: Optional[List[str]] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> Any:
        """사내지식 검색 도구 실행"""
        if system_codes is None:
            from src.utils.config_utils import ConfigUtils

            system_codes = ConfigUtils.get_default_system_codes()

        arguments = {"query": query, "system_codes": system_codes, "top_k": top_k}

        ServiceLogger.debug(f"사내지식 검색 실행: {query[:50]}...")
        return await self.call_tool(
            client_name="lgenie",
            tool_name="retrieve_coporate_knowledge",  # 실제 MCP 서버 도구 이름 사용
            arguments=arguments,
            sso_id=sso_id,
        )

    async def call_mcp_tool_with_validation(
        self,
        tool_name: str,
        client_name: str,
        args: Dict[str, Any],
        sso_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP 도구를 스키마 검증과 함께 실행하는 통일된 메서드"""
        from src.agents.components.search_agent.mcp_handler import MCPHandler
        from src.capabilities.tool_schemas import ToolSchemaManager

        try:
            # ServiceLogger.debug(f"스키마 검증과 함께 도구 실행: {tool_name}")

            # MCPHandler 인스턴스 생성
            mcp_handler = MCPHandler()

            # 내부 도구 이름을 실제 MCP 서버 도구 이름으로 매핑
            mcp_tool_name = self._map_tool_name_to_mcp(tool_name)

            # 도구 정보 구성
            tool_info = {
                "name": mcp_tool_name,  # 실제 MCP 서버 도구 이름 사용
                "client": client_name,
                "provider": "mcp",
                "input_schema": ToolSchemaManager.get_tool_schema(
                    tool_name
                ),  # 내부 도구 이름으로 스키마 조회
            }

            # 사용자 컨텍스트 구성
            user_context = {"sso_id": sso_id} if sso_id else {}

            # MCP 도구 실행
            result = await mcp_handler.execute_tool(
                tool_name=tool_name,
                tool_info=tool_info,
                args=args,
                user_context=user_context,
            )

            # ServiceLogger.debug(f"스키마 검증 도구 실행 완료: {tool_name}")
            return result

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            raise e

        except Exception as e:
            ServiceLogger.error(f"스키마 검증 도구 실행 실패 - {tool_name}: {e}")
            raise MCPToolError(f"스키마 검증 도구 실행 실패 - {tool_name}: {e}") from e

    async def call_corporate_knowledge_tool(
        self,
        query: str,
        sso_id: Optional[str] = None,
        system_codes: Optional[List[str]] = None,
        top_k: int = 5,
    ) -> Any:
        """사내지식 검색 도구 실행"""
        if system_codes is None:
            from src.utils.config_utils import ConfigUtils

            system_codes = ConfigUtils.get_default_system_codes()

        arguments = {"query": query, "system_codes": system_codes, "top_k": top_k}

        return await self.call_tool(
            client_name="lgenie",
            tool_name="retrieve_corporate_knowledge",
            arguments=arguments,
            sso_id=sso_id,
        )

    async def call_mcp_tool_with_validation(
        self,
        tool_name: str,
        client_name: str,
        args: Dict[str, Any],
        sso_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP 도구를 스키마 검증과 함께 실행하는 통일된 메서드"""
        from src.agents.components.search_agent.mcp_handler import MCPHandler

        # MCPHandler 인스턴스 생성
        mcp_handler = MCPHandler()

        # 도구 정보 구성
        tool_info = {
            "name": tool_name,
            "client": client_name,
            "provider": "mcp",
            "input_schema": self._get_tool_schema(tool_name),
        }

        # 사용자 컨텍스트 구성
        user_context = {"sso_id": sso_id} if sso_id else {}

        # MCP 도구 실행
        return await mcp_handler.execute_tool(
            tool_name=tool_name,
            tool_info=tool_info,
            args=args,
            user_context=user_context,
        )

    def _get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """도구별 스키마 정의"""
        schemas = {
            "retrieve_coporate_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "system_codes": {"type": "array", "items": {"type": "string"}},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query", "system_codes", "top_k"],
            },
            "retrieve_personal_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "get_events": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "start_date_time": {"type": "string"},
                    "end_date_time": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": [],
            },
            "get_mails": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": [],
            },
            "send_mail": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            "get_employee_infos_from_human_question": {
                "type": "object",
                "properties": {"human_question": {"type": "string"}},
                "required": ["human_question"],
            },
            "get_olap_search_data": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "cube_name": {"type": "string"},
                },
                "required": ["query", "cube_name"],
            },
            "retrieve_scm_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "get_web_search_data": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        }

        return schemas.get(
            tool_name, {"type": "object", "properties": {}, "required": []}
        )

    async def close(self) -> None:
        """MCP 서비스 종료"""
        if self.initialized:
            # ServiceLogger.debug("MCP 서비스 종료 시작")
            await mcp_manager.close_all()
            self.initialized = False
            # ServiceLogger.debug("MCP 서비스 종료 완료")


# 전역 MCP 서비스 인스턴스
mcp_service = MCPService()
