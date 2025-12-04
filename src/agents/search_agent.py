"""
검색 에이전트 - 실시간 스트리밍 지원
"""

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.agents.components.common.tool_registry import ToolRegistry
from src.agents.components.search_agent.mcp_handler import MCPHandler
from src.agents.components.search_agent.search_agent_planner import SearchAgentPlanner
from src.agents.components.search_agent.tool_executor import ToolExecutor
from src.agents.components.search_agent.tool_result_converter import (
    ToolResultConverter,
)
from src.schemas.sse_response import SSEResponse
from src.schemas.tool_result_schema import UnifiedToolResult
from src.utils.log_collector import collector
from src.utils.timezone_utils import get_current_time_in_timezone

logger = logging.getLogger("search_agent")


class SearchAgentWrapper:
    """독립적인 검색 에이전트"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.logger = logger
        self.config = config or {}

        # agent_id나 agent_code를 config에서 가져오기
        self.agent_id = self.config.get("agent_id")
        self.agent_code = self.config.get("agent_code")

        # planner config에 agent_id나 agent_code 추가
        planner_config = self.config.get("planner", {})
        if self.agent_id:
            planner_config["agent_id"] = self.agent_id
        if self.agent_code:
            planner_config["agent_code"] = self.agent_code

        # 검색 에이전트 컴포넌트들 초기화
        self.planner = SearchAgentPlanner(
            config=planner_config,
            agent_id=self.agent_id,
            agent_code=self.agent_code,
        )
        self.mcp_handler = MCPHandler()
        self.tool_executor = ToolExecutor()
        self.llm_converter = ToolResultConverter()

        self.logger.debug("[SEARCH_AGENT] 검색 에이전트가 초기화되었습니다")

    async def _run_search_logic(
        self,
        *,
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """의도/쿼리를 받아 플래닝→도구실행→압축까지 수행한 구조화 결과 반환"""
        # 1. MCP 서버 연결 확인 및 도구 목록 준비
        available_tools_meta = await self._prepare_available_tools()

        # 2. Planning
        # agent_id가 없으면 planner의 agent_id 사용 (planner가 LLMComponent를 상속받아 agent_id를 가짐)
        plan_agent_id = self.agent_id
        if not plan_agent_id and hasattr(self.planner, 'agent_id'):
            plan_agent_id = self.planner.agent_id
        
        if not plan_agent_id:
            raise ValueError("agent_id가 필요합니다. SearchAgentWrapper 초기화 시 agent_id 또는 agent_code를 전달하세요.")
        
        plan = await self.planner.plan(
            query=query,
            user_context=user_context or {},
            available_tools=available_tools_meta,
            agent_id=plan_agent_id,
        )
        self.logger.debug("[SEARCH_AGENT] 검색 계획을 수립했습니다")

        # 계획이 비어있으면 바로 return
        if not isinstance(plan, list) or not plan:
            self.logger.debug("[SEARCH_AGENT] 툴 사용이 필요없습니다. 바로 답변합니다.")
            return {
                "plan": plan,
                "tool_results": [],
                "summary": [],
            }

        # 3. Execute tools by plan
        tool_results = await self._execute_plan(
            plan, query, user_context, available_tools_meta
        )

        # tool 결과가 비어있으면 바로 return
        if not tool_results:
            self.logger.error(
                "[SEARCH_AGENT] 도구 실행 결과가 비어있습니다. 검색 결과를 찾을 수 없습니다."
            )
            return {
                "plan": plan,
                "tool_results": tool_results,
                "unified_tool_results": [],
                "summary": [],
            }

        # 4. Convert tool results to unified schema
        unified_tool_results = await self._convert_tool_results(
            tool_results, query, user_context
        )

        # 5. Compress results
        summary = await self._compress_results(
            query, user_context, unified_tool_results
        )

        return {
            "plan": plan,
            "tool_results": tool_results,
            "unified_tool_results": unified_tool_results,
            "summary": summary,
        }

    async def _prepare_available_tools(self) -> List[Dict[str, Any]]:
        """사용 가능한 도구 목록을 준비합니다"""
        # 1. MCP 서버 연결 확인
        self.logger.debug("[SEARCH_AGENT] MCP 서버 연결 상태를 확인합니다...")
        mcp_status = await self.mcp_handler.check_connection()
        self.logger.debug(f"[SEARCH_AGENT] MCP 연결 상태: {mcp_status['message']}")

        # 2. 기본 도구 목록 가져오기
        try:
            available_tools_meta = ToolRegistry.get_available_tools()
        except Exception:
            available_tools_meta = []

        # 3. MCP 도구들을 기본 도구 목록에 추가 (사용할 도구만 필터링)
        if mcp_status["connected"] and mcp_status["tools"]:
            mcp_tools = mcp_status["tools"]

            # 사용할 MCP 도구 목록 (화이트리스트)
            allowed_mcp_tools = {
                "get_mails",
                "get_events",
                "retrieve_coporate_knowledge",
            }

            # 사용할 도구만 필터링
            filtered_tools = []
            for tool in mcp_tools:
                tool_name = tool.get("name", "")
                if tool_name in allowed_mcp_tools:
                    filtered_tools.append(tool)
                    self.logger.debug(f"[SEARCH_AGENT] 허용된 도구 추가: {tool_name}")
                else:
                    self.logger.debug(f"[SEARCH_AGENT] 제외된 도구: {tool_name}")

            self.logger.info(
                f"[SEARCH_AGENT] MCP 도구 {len(mcp_tools)}개 중 {len(filtered_tools)}개 사용 가능 도구를 planning에 추가합니다"
            )

            # MCP 도구들을 available_tools_meta 형식에 맞게 변환
            for mcp_tool in filtered_tools:
                tool_name = mcp_tool.get("name", "")
                if not tool_name:  # 도구 이름이 없으면 건너뛰기
                    self.logger.warning(
                        f"[SEARCH_AGENT] 도구 이름이 비어있어 건너뜀: {mcp_tool}"
                    )
                    continue

                tool_meta = {
                    "name": tool_name,
                    "description": mcp_tool.get("description", ""),
                    "provider": "mcp",
                    "client": mcp_tool.get("client", ""),
                    "input_schema": mcp_tool.get("input_schema", {}),
                    "output_schema": mcp_tool.get("output_schema", {}),
                }
                available_tools_meta.append(tool_meta)
                self.logger.debug(f"[SEARCH_AGENT] 도구 메타데이터 추가: {tool_name}")

            self.logger.debug(
                f"[SEARCH_AGENT] 총 {len(available_tools_meta)}개 도구가 planning에 전달됩니다"
            )
            collector.log("tool_list", available_tools_meta)
        else:
            self.logger.warning(
                "[SEARCH_AGENT] MCP 서버 연결 실패로 MCP 도구를 사용할 수 없습니다"
            )

        return available_tools_meta

    async def _execute_plan(
        self,
        plan: List[Dict[str, Any]],
        query: str,
        user_context: Optional[Dict[str, Any]],
        available_tools_meta: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """계획에 따라 도구들을 실행합니다"""
        tool_results: List[Dict[str, Any]] = []

        for i, step in enumerate(plan, 1):
            tool_name = str(step.get("tool") or "").strip()
            if not tool_name or tool_name == "Unknown":
                self.logger.warning(
                    f"[SEARCH_AGENT] Step {i}: 유효하지 않은 도구명: '{tool_name}'"
                )
                continue

            # 허용된 도구 목록 확인
            allowed_tools = {
                "get_mails",
                "get_events",
                "retrieve_coporate_knowledge",
                "llm_knowledge",
                "web_search",
            }
            if tool_name not in allowed_tools:
                self.logger.warning(
                    f"[SEARCH_AGENT] Step {i}: 허용되지 않은 도구: '{tool_name}'"
                )
                continue

            args = step.get("args") or {}
            if not isinstance(args, dict):
                args = {"input": args}

            self.logger.debug(
                f"[SEARCH_AGENT] Step {i}: 도구 '{tool_name}' 실행 시작 (args: {args})"
            )

            # 도구 실행
            result = await self.tool_executor.execute_tool(
                tool_name=tool_name,
                args=args,
                query=query,
                user_context=user_context,
                available_tools_meta=available_tools_meta,
            )

            if result:
                # 도구 실행 결과 로깅
                is_error = result.get("is_error", False)
                raw_result = result.get("result", "")

                # ToolError 객체인 경우도 에러로 처리
                if (
                    hasattr(raw_result, "__class__")
                    and "Error" in raw_result.__class__.__name__
                ):
                    is_error = True

                execution_time = result.get("duration", 0)
                result_size = len(str(raw_result))

                if is_error:
                    # 에러 메시지 추출
                    error_message = result.get("error_message", "Unknown error")
                    if hasattr(raw_result, "message"):
                        error_message = raw_result.message
                    elif hasattr(raw_result, "args") and raw_result.args:
                        error_message = str(raw_result.args[0])
                    elif str(raw_result) != str(type(raw_result)):
                        error_message = str(raw_result)

                    self.logger.warning(
                        f"[SEARCH_AGENT] Step {i}: 도구 '{tool_name}' 실행 실패 "
                        f"(시간: {execution_time:.3f}초, 오류: {error_message})"
                    )

                else:
                    self.logger.debug(
                        f"[SEARCH_AGENT] Step {i}: 도구 '{tool_name}' 실행 완료 "
                        f"(시간: {execution_time:.3f}초, 결과 크기: {result_size}자)"
                    )

                    # 결과 미리보기 로깅
                    raw_result = result.get("result", "")
                    try:
                        if isinstance(raw_result, dict):
                            preview = (
                                str(raw_result)[:200] + "..."
                                if len(str(raw_result)) > 200
                                else str(raw_result)
                            )
                        else:
                            preview = (
                                str(raw_result)[:200] + "..."
                                if len(str(raw_result)) > 200
                                else str(raw_result)
                            )
                        self.logger.debug(
                            f"[SEARCH_AGENT] Tool {tool_name}: 결과 - {preview}"
                        )
                    except Exception as preview_error:
                        # 결과 미리보기 생성 실패 시 간단한 정보만 로깅
                        result_type = type(raw_result).__name__
                        self.logger.debug(
                            f"[SEARCH_AGENT] Step {i}: 결과 미리보기 생성 실패 "
                            f"(타입: {result_type}, 오류: {preview_error})"
                        )

                tool_results.append(result)
            else:
                self.logger.error(
                    f"[SEARCH_AGENT] Step {i}: 도구 '{tool_name}' 실행 결과가 None입니다"
                )

        return tool_results

    async def _convert_tool_results(
        self,
        tool_results: List[Dict[str, Any]],
        query: str,
        user_context: Optional[Dict[str, Any]],
    ) -> List[UnifiedToolResult]:
        """도구 실행 결과를 통일된 스키마로 변환합니다"""
        self.logger.debug(f"[SEARCH_AGENT] {len(tool_results)}개 도구 결과를 포맷팅")

        try:
            # 룰 기반 변환기로 일괄 변환
            unified_results = self.llm_converter.convert_multiple_tool_results(
                tool_results=tool_results,
                query=query,
                user_context=user_context,
            )

            # 변환 결과 통계 로깅
            self.logger.debug(
                f"[SEARCH_AGENT] 변환 통계 - 총 {len(unified_results)}개 도구 결과 변환 완료"
            )

            return unified_results

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT] LLM 변환 전체 실패: {e}")
            # 전체 변환 실패 시 빈 리스트 반환
            return []

    async def _compress_results(
        self,
        query: str,
        user_context: Optional[Dict[str, Any]],
        unified_tool_results: List[UnifiedToolResult],
    ) -> str:
        """도구 실행 결과를 압축합니다"""
        # 간단한 fallback 방식으로 결과 압축
        summary_parts: List[str] = []
        for tr in unified_tool_results:
            summary_parts.append(f"[{tr.tool_name}] {tr.formatted_result[:400]}")
        summary = "\n".join(summary_parts)[:2000]

        self.logger.debug(f"[SEARCH_AGENT] 결과 압축 완료: {len(summary)}자")
        return summary

    async def run_search(
        self,
        query: str,
        user_id: int,
        actual_user_id: str,
        session_id: str,
        user_context: Optional[Dict[str, Any]] = None,
        intent: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        검색을 실행하고 실시간 스트리밍으로 결과를 반환합니다.

        Args:
            query: 검색 쿼리
            user_id: 사용자 ID
            actual_user_id: 실제 사용자 ID
            session_id: 세션 ID
            user_context: 사용자 컨텍스트
            intent: 의도 분석 결과

        Yields:
            str: SSE 응답 문자열
        """
        self.logger.debug("[SEARCH_AGENT] 검색을 시작합니다")

        try:
            # 진행 상태 알림
            yield await SSEResponse.create_progress(
                progress=0.1, message="검색 계획을 수립하고 있습니다..."
            ).send()

            # 사용자 컨텍스트에 의도 정보 추가
            if user_context is None:
                user_context = {}

            if intent:
                user_context = {**user_context, "intent": intent}

            # 검색 에이전트 실행
            yield await SSEResponse.create_progress(
                progress=0.3, message="도구를 실행하고 있습니다..."
            ).send()

            result = await self._run_search_logic(
                query=query, user_context=user_context
            )

            yield await SSEResponse.create_progress(
                progress=0.7, message="검색 결과를 압축하고 있습니다..."
            ).send()

            # 결과 처리
            plan = result.get("plan", [])
            tool_results = result.get("tool_results", [])
            summary = result.get("summary", "")

            # 검색 결과를 SSE로 스트리밍
            if tool_results:
                for i, tool_result in enumerate(tool_results):
                    tool_name = tool_result.get("tool", "unknown")
                    tool_summary = tool_result.get("result", "")

                    # 각 도구 결과를 개별적으로 스트리밍
                    yield await SSEResponse.create_message(
                        message_id=f"search_{i}",
                        content=f"[{tool_name}] {str(tool_summary)[:500]}...",
                        role="assistant",
                        done=False,
                    ).send()

            # 최종 요약
            yield await SSEResponse.create_progress(
                progress=0.9, message="최종 답변을 생성하고 있습니다..."
            ).send()

            if summary:
                yield await SSEResponse.create_message(
                    message_id="search_summary",
                    content=summary,
                    role="assistant",
                    done=True,
                ).send()
            else:
                # 요약이 없는 경우 도구 결과들을 합쳐서 답변 생성
                combined_results = []
                for tool_result in tool_results:
                    tool_name = tool_result.get("tool", "unknown")
                    result_content = str(tool_result.get("result", ""))
                    combined_results.append(f"[{tool_name}] {result_content}")

                final_content = (
                    "\n\n".join(combined_results)
                    if combined_results
                    else "검색 결과를 찾을 수 없습니다."
                )

                yield await SSEResponse.create_message(
                    message_id="search_final",
                    content=final_content,
                    role="assistant",
                    done=True,
                ).send()

            # 완료 알림
            yield await SSEResponse.create_progress(
                progress=1.0, message="검색이 완료되었습니다."
            ).send()

            self.logger.debug("[SEARCH_AGENT] 검색이 완료되었습니다")

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT] 검색 실행 중 오류: {e}")
            yield await SSEResponse.create_error(
                f"검색 실행 중 오류가 발생했습니다: {str(e)}"
            ).send()
            raise e

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LangGraph 노드에서 사용할 수 있는 검색 실행 메서드
        실시간 스트리밍은 별도로 처리하고, 최종 결과만 반환합니다.
        """
        self.logger.debug("[SEARCH_AGENT] LangGraph용 검색을 시작합니다")

        try:
            messages = state.get("messages", [])
            if messages:
                last_message = messages[-1]
                query = getattr(last_message, "content", "")
            else:
                query = ""
            user_context = state.get("user_context", {})
            intent = state.get("intent")

            # 사용자 컨텍스트에 의도 정보 추가
            if intent:
                user_context = {**user_context, "intent": intent}

            # 검색 에이전트 실행
            result = await self._run_search_logic(
                query=query, user_context=user_context
            )

            self.logger.debug("[SEARCH_AGENT] LangGraph용 검색이 완료되었습니다")

            # LangGraph 상태에 필요한 필드들만 반환
            return {
                "search_agent_output": {
                    "plan": result.get("plan", []),
                    "tool_results": result.get("tool_results", []),
                    "unified_tool_results": result.get("unified_tool_results", []),
                    "summary": result.get("summary", ""),
                },
                "search_completed": True,
            }

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT] LangGraph용 검색 중 오류: {e}")
            return {
                "search_agent_output": {
                    "plan": [],
                    "tool_results": [],
                    "unified_tool_results": [],
                    "summary": f"검색 실행 중 오류가 발생했습니다: {str(e)}",
                },
                "search_completed": False,
                "error": str(e),
            }

    async def test_mcp_connection(self) -> Dict[str, Any]:
        """MCP 서버 연결 테스트를 수행합니다."""
        self.logger.debug("[SEARCH_AGENT] MCP 서버 연결 테스트를 시작합니다...")

        try:
            # MCP 핸들러를 통해 테스트 수행
            result = await self.mcp_handler.test_connection()

            # Planning 도구 통합 확인 추가
            try:
                available_tools_meta = ToolRegistry.get_available_tools()
                mcp_status = result.get("mcp_connection", {})
                total_tools = len(available_tools_meta) + len(
                    mcp_status.get("tools", [])
                )

                result["steps"].append(
                    {
                        "step": 3,
                        "name": "Planning 도구 통합 확인",
                        "status": "success",
                        "message": f"총 {total_tools}개 도구가 planning에 전달됨",
                        "details": {
                            "basic_tools": len(available_tools_meta),
                            "mcp_tools": len(mcp_status.get("tools", [])),
                            "total_tools": total_tools,
                        },
                    }
                )
            except Exception as e:
                result["steps"].append(
                    {
                        "step": 3,
                        "name": "Planning 도구 통합 확인",
                        "status": "failed",
                        "message": f"기본 도구 목록 조회 실패: {str(e)}",
                        "details": {},
                    }
                )

            self.logger.debug(
                f"[SEARCH_AGENT] MCP 연결 테스트 완료: {result['summary']}"
            )
            return result

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT] MCP 연결 테스트 중 오류: {e}")
            return {
                "test_name": "MCP 서버 연결 테스트",
                "timestamp": get_current_time_in_timezone().isoformat(),
                "overall_status": "error",
                "error": str(e),
                "summary": f"MCP 연결 테스트 중 오류 발생: {str(e)}",
            }

    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보를 반환합니다."""
        return {
            "name": "SearchAgent",
            "description": "검색 에이전트 - 웹 검색 및 도구 실행",
            "capabilities": [
                "웹 검색",
                "도구 계획 수립",
                "도구 실행",
                "결과 압축 및 요약",
                "실시간 스트리밍",
                "MCP 서버 연결 및 도구 실행",
            ],
            "supported_intents": ["search", "information", "general"],
        }
