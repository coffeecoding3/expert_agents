"""
MCP 서버 연결 및 도구 실행을 담당하는 핸들러
"""

import logging
from typing import Any, Dict, List, Optional

from src.capabilities.mcp_service import mcp_service
from src.utils.mcp_utils import get_default_mcp_value, validate_mcp_tool_args
from src.utils.result_utils import get_result_summary
from src.utils.timezone_utils import get_current_time_in_timezone, get_timestamp

logger = logging.getLogger("mcp_handler")


class MCPHandler:
    """MCP 서버 연결 및 도구 실행을 담당하는 클래스"""

    def __init__(self):
        self.logger = logger

    async def ensure_initialized(self):
        """MCP 서비스가 초기화되었는지 확인하고 필요시 초기화"""
        if not mcp_service.initialized:
            await mcp_service.initialize()

    async def check_connection(self) -> Dict[str, Any]:
        """MCP 서버 연결 상태 확인"""
        try:
            # MCP 서비스 초기화 확인
            await self.ensure_initialized()

            # MCP 서버 연결 테스트
            available_tools = await mcp_service.get_available_tools()
            self.logger.info(f"[MCP_HANDLER] available_tools: {available_tools}")

            return {
                "connected": True,
                "tools_count": len(available_tools),
                "tools": available_tools,
                "message": f"MCP 서버 연결 성공. {len(available_tools)}개 도구 사용 가능",
            }
        except Exception as e:
            self.logger.error(f"[MCP_HANDLER] MCP 서버 연결 실패: {e}")
            return {
                "connected": False,
                "tools_count": 0,
                "tools": [],
                "message": f"MCP 서버 연결 실패: {str(e)}",
            }

    def _get_result_summary(self, result: Any) -> str:
        """실행 결과를 짧게 요약해서 반환"""
        return get_result_summary(result)

    def is_mcp_tool(
        self, tool_name: str, available_tools_meta: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """도구가 MCP 도구인지 확인하고 정보 반환"""
        for tool_meta in available_tools_meta:
            if (
                tool_meta.get("name") == tool_name
                and tool_meta.get("provider") == "mcp"
            ):
                return tool_meta
        return None

    def validate_tool_args(
        self, tool_name: str, args: Dict[str, Any], input_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MCP 도구의 input schema에 맞게 파라미터 검증 및 정규화"""
        return validate_mcp_tool_args(tool_name, args, input_schema)

    async def execute_tool(
        self,
        tool_name: str,
        tool_info: Dict[str, Any],
        args: Dict[str, Any],
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """MCP 도구 실행"""
        try:
            self.logger.debug(f"[MCP_HANDLER] MCP 도구 {tool_name}을 실행합니다")

            # Input schema에 맞게 파라미터 검증 및 정규화
            validated_args = self.validate_tool_args(
                tool_name,
                args,
                tool_info.get("input_schema", {}),
            )

            # Tool 실행 시간 측정 시작
            tool_start_time = get_timestamp()

            # 디버깅을 위한 로그 추가
            sso_id = user_context.get("sso_id") if user_context else None
            self.logger.debug(f"[MCP_HANDLER] user_context: {user_context}")
            self.logger.debug(f"[MCP_HANDLER] sso_id: {sso_id}")

            result = await mcp_service.call_tool(
                client_name=tool_info.get("client", ""),
                tool_name=tool_name,
                arguments=validated_args,
                sso_id=sso_id,
            )

            tool_duration = get_timestamp() - tool_start_time

            # 결과가 오류인지 확인
            is_error = False
            error_type = None
            error_message = None

            if isinstance(result, dict) and "error_type" in result:
                is_error = True
                error_type = result.get("error_type")
                error_message = result.get("message", "알 수 없는 오류")
                self.logger.warning(
                    f"[MCP_HANDLER] MCP 도구 {tool_name} 오류 응답 수신 - "
                    f"타입: {error_type}, 메시지: {error_message}"
                )
            else:
                self.logger.info(f"[MCP_HANDLER] MCP 도구 {tool_name} 실행 완료")
                self.logger.debug(f"[MCP_HANDLER] result: {result}")

            return {
                "tool": tool_name,
                "search_query": args.get("query", ""),
                "parameters": validated_args,
                "result": result,
                "duration": tool_duration,
                "provider": "mcp",
                "client": tool_info.get("client", ""),
                "is_error": is_error,
                "error_type": error_type,
                "error_message": error_message,
            }

        except Exception as e:
            tool_duration = (
                get_timestamp() - tool_start_time
                if "tool_start_time" in locals()
                else 0.0
            )
            self.logger.error(f"[MCP_HANDLER] MCP 도구 {tool_name} 실행 실패: {e}")
            raise e

    async def test_connection(self) -> Dict[str, Any]:
        """MCP 서버 연결 테스트를 수행합니다."""
        self.logger.debug("[MCP_HANDLER] MCP 서버 연결 테스트를 시작합니다...")

        try:
            # 1. MCP 서버 연결 확인
            mcp_status = await self.check_connection()

            result = {
                "test_name": "MCP 서버 연결 테스트",
                "timestamp": get_current_time_in_timezone().isoformat(),
                "mcp_connection": mcp_status,
                "steps": [],
            }

            # 2. 연결 상태 로깅
            result["steps"].append(
                {
                    "step": 1,
                    "name": "MCP 서버 연결 확인",
                    "status": "success" if mcp_status["connected"] else "failed",
                    "message": mcp_status["message"],
                    "details": {
                        "tools_count": mcp_status["tools_count"],
                        "tools_available": len(mcp_status["tools"]) > 0,
                    },
                }
            )

            # 3. 도구 목록 확인
            if mcp_status["connected"]:
                tools_info = []
                for tool in mcp_status["tools"]:
                    tools_info.append(
                        {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "client": tool.get("client", ""),
                            "has_input_schema": bool(tool.get("input_schema")),
                            "has_output_schema": bool(tool.get("output_schema")),
                        }
                    )

                result["steps"].append(
                    {
                        "step": 2,
                        "name": "MCP 도구 목록 확인",
                        "status": "success",
                        "message": f"{len(tools_info)}개 도구 확인됨",
                        "details": {"tools": tools_info},
                    }
                )

            result["overall_status"] = (
                "success" if mcp_status["connected"] else "failed"
            )
            result["summary"] = (
                f"MCP 서버 연결 테스트 완료. 연결 상태: {'성공' if mcp_status['connected'] else '실패'}"
            )

            self.logger.info(f"[MCP_HANDLER] MCP 연결 테스트 완료: {result['summary']}")
            return result

        except Exception as e:
            self.logger.error(f"[MCP_HANDLER] MCP 연결 테스트 중 오류: {e}")
            return {
                "test_name": "MCP 서버 연결 테스트",
                "timestamp": get_current_time_in_timezone().isoformat(),
                "overall_status": "error",
                "error": str(e),
                "summary": f"MCP 연결 테스트 중 오류 발생: {str(e)}",
            }
