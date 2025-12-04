"""
MCP Registry Manager
MCP 서버 레지스트리를 동적으로 관리하는 매니저
"""

from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.capabilities.logging_utils import RegistryLogger
from src.capabilities.exceptions import MCPRegistryError
from src.capabilities.constants import REGISTRY_FILE_NOT_FOUND, SCOPE_UPDATE_FAILED


class MCPRegistryManager:
    """MCP 서버 레지스트리 매니저"""

    def __init__(self, registry_path: str = "src/capabilities/registry.yaml"):
        self.registry_path = Path(registry_path)
        self.registry_data: Dict[str, Any] = {}

    def load_registry(self) -> Dict[str, Any]:
        """레지스트리 파일 로드"""
        if not self.registry_path.exists():
            RegistryLogger.warning(f"{REGISTRY_FILE_NOT_FOUND}: {self.registry_path}")
            return {}

        try:
            RegistryLogger.debug(f"레지스트리 파일 로드: {self.registry_path}")
            with open(self.registry_path, "r", encoding="utf-8") as f:
                self.registry_data = yaml.safe_load(f) or {}
            RegistryLogger.info("레지스트리 파일 로드 완료")
            return self.registry_data
        except Exception as e:
            RegistryLogger.error(f"레지스트리 파일 로드 실패: {e}")
            raise MCPRegistryError(f"레지스트리 파일 로드 실패: {e}") from e

    def save_registry(self) -> None:
        """레지스트리 파일 저장"""
        try:
            RegistryLogger.debug(f"레지스트리 파일 저장: {self.registry_path}")
            with open(self.registry_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    self.registry_data, f, default_flow_style=False, allow_unicode=True
                )
            RegistryLogger.info("레지스트리 파일 저장 완료")
        except Exception as e:
            RegistryLogger.error(f"레지스트리 파일 저장 실패: {e}")
            raise MCPRegistryError(f"레지스트리 파일 저장 실패: {e}") from e

    async def update_client_scope(self, client_name: str, mcp_service=None) -> List[str]:
        """클라이언트의 scope를 동적으로 업데이트"""
        try:
            if mcp_service is None:
                # 지연 import로 순환 참조 방지
                from src.capabilities.mcp_service import mcp_service as _mcp_service
                mcp_service = _mcp_service
            
            RegistryLogger.debug(f"클라이언트 scope 업데이트 시작: {client_name}")
            scope = mcp_service.get_client_scope(client_name)

            # 레지스트리 업데이트
            if (
                "servers" in self.registry_data
                and "external" in self.registry_data["servers"]
            ):
                if client_name in self.registry_data["servers"]["external"]:
                    self.registry_data["servers"]["external"][client_name][
                        "scope"
                    ] = scope
                    RegistryLogger.info(f"{client_name} scope 업데이트: {scope}")

            return scope
        except Exception as e:
            RegistryLogger.error(f"{SCOPE_UPDATE_FAILED} - {client_name}: {e}")
            return []

    async def update_all_scopes(self, mcp_service=None) -> Dict[str, List[str]]:
        """모든 클라이언트의 scope 업데이트"""
        scopes = {}

        try:
            RegistryLogger.debug("모든 클라이언트 scope 업데이트 시작")
            
            # 레지스트리에서 외부 서버 목록 가져오기
            if (
                "servers" in self.registry_data
                and "external" in self.registry_data["servers"]
            ):
                for client_name in self.registry_data["servers"]["external"].keys():
                    scope = await self.update_client_scope(client_name, mcp_service)
                    scopes[client_name] = scope
                    
            RegistryLogger.info(f"모든 클라이언트 scope 업데이트 완료: {len(scopes)}개")
            return scopes
        except Exception as e:
            RegistryLogger.error(f"모든 클라이언트 scope 업데이트 실패: {e}")
            return scopes

    def get_client_config(self, client_name: str) -> Dict[str, Any]:
        """클라이언트 설정 반환"""
        try:
            if (
                "servers" in self.registry_data
                and "external" in self.registry_data["servers"]
            ):
                config = self.registry_data["servers"]["external"].get(client_name, {})
                RegistryLogger.debug(f"클라이언트 설정 조회: {client_name}")
                return config
            return {}
        except Exception as e:
            RegistryLogger.error(f"클라이언트 설정 조회 실패 - {client_name}: {e}")
            return {}

    def get_all_client_configs(self) -> Dict[str, Dict[str, Any]]:
        """모든 외부 클라이언트 설정 반환"""
        try:
            if (
                "servers" in self.registry_data
                and "external" in self.registry_data["servers"]
            ):
                configs = self.registry_data["servers"]["external"]
                RegistryLogger.debug(f"모든 클라이언트 설정 조회: {len(configs)}개")
                return configs
            return {}
        except Exception as e:
            RegistryLogger.error(f"모든 클라이언트 설정 조회 실패: {e}")
            return {}


# 전역 레지스트리 매니저 인스턴스
registry_manager = MCPRegistryManager()
