"""
MCP Client Manager
MCP 클라이언트들을 관리하는 매니저 클래스
"""

from typing import Any, Dict, List, Optional

from src.schemas.raih_exceptions import (
    RAIHAuthorizationException,
    RAIHBusinessException,
)
from .mcp_client import MCPClient
from src.capabilities.logging_utils import ClientLogger
from src.capabilities.exceptions import MCPClientError
from src.capabilities.constants import DEFAULT_TIMEOUT, DEFAULT_RETRY_ATTEMPTS


class MCPClientManager:
    """MCP 클라이언트들을 관리하는 매니저"""

    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
        self._initialized = False

    def _create_client_from_config(self, config: Dict[str, Any]) -> MCPClient:
        """설정에서 MCP 클라이언트 생성"""
        return MCPClient(
            endpoint=config.get("endpoint"),
            api_key=config.get("api_key"),
            headers=config.get("headers"),
            timeout=config.get("timeout", DEFAULT_TIMEOUT),
            retry_attempts=config.get("retry_attempts", DEFAULT_RETRY_ATTEMPTS),
        )

    async def _initialize_client(self, client: MCPClient, name: str) -> bool:
        """클라이언트 초기화"""
        try:
            ClientLogger.debug(f"{name} MCP 클라이언트 초기화 시작")
            await client.initialize()

            # 도구 목록 조회 시도
            try:
                tools = await client.list_tools()
                ClientLogger.debug(f"{name} 클라이언트에서 {len(tools)}개 도구 발견")
            except Exception as tool_error:
                ClientLogger.warning(
                    f"{name} 클라이언트 도구 목록 조회 실패", error=str(tool_error)
                )

            self.clients[name] = client
            ClientLogger.debug(f"{name} MCP 클라이언트 초기화 완료")
            return True
        except Exception as e:
            ClientLogger.error(f"{name} MCP 클라이언트 초기화 실패", error=str(e))
            await client.close()
            return False

    def get_client_scope(self, client_name: str) -> List[str]:
        """클라이언트의 도구 이름 목록 반환 (scope용)"""
        client = self.clients.get(client_name)
        if client:
            return client.get_tool_names()
        return []

    async def initialize_from_config(self, config: Dict[str, Any]):
        """설정에서 MCP 클라이언트들을 초기화"""
        if self._initialized:
            ClientLogger.debug("이미 초기화됨, 건너뛰기")
            return

        lgenie_config = config.get("lgenie_mcp")
        if (
            lgenie_config
            and lgenie_config.get("endpoint")
            and lgenie_config.get("api_key")
        ):
            client = self._create_client_from_config(lgenie_config)
            success = await self._initialize_client(client, "lgenie")
            if not success:
                ClientLogger.warning("lgenie 클라이언트 초기화 실패 - 도구 사용 불가")
        else:
            ClientLogger.warning(
                "lgenie_mcp 설정이 없거나 불완전합니다. "
                "환경 변수 LGENIE_MCP_ENDPOINT와 LGENIE_MCP_API_KEY를 확인하세요."
            )

        self._initialized = True
        # ClientLogger.debug("매니저 초기화 완료")

    async def get_client(self, name: str) -> Optional[MCPClient]:
        """이름으로 클라이언트 가져오기"""
        return self.clients.get(name)

    async def call_tool(
        self,
        client_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        sso_id: Optional[str] = None,
    ) -> Any:
        """클라이언트의 도구 실행"""
        client = await self.get_client(client_name)
        try:
            if not client:
                raise MCPClientError(
                    f"MCP 클라이언트를 찾을 수 없습니다: {client_name}"
                )

            return await client.call_tool(tool_name, arguments, sso_id)

        except (RAIHAuthorizationException, RAIHBusinessException) as e:
            raise e

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        """모든 클라이언트의 도구 목록 반환"""
        all_tools = []
        for client_name, client in self.clients.items():
            for tool in client.available_tools:
                all_tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "output_schema": tool.output_schema,
                        "client": client_name,
                        "provider": "mcp",
                    }
                )
        return all_tools

    async def close_all(self):
        """모든 클라이언트 종료"""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        self._initialized = False


# 전역 MCP 클라이언트 매니저 인스턴스
mcp_manager = MCPClientManager()
