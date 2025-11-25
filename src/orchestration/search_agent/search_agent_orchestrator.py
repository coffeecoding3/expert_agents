"""
Search Agent Orchestrator
검색 에이전트 오케스트레이터
"""

import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph
from langchain_core.messages import AIMessage
from src.agents.nodes.search_agent.search_agent_compress_node import (
    SearchAgentCompressionNode,
)
from src.agents.nodes.search_agent.search_execution_node import SearchAgentExecutionNode
from src.agents.nodes.search_agent.search_planning_node import SearchAgentPlanningNode
from src.orchestration.common.base_orchestrator import BaseOrchestrator
from src.orchestration.states.search_state import SearchState
from src.schemas.raih_exceptions import RAIHBusinessException, RAIHAuthorizationException

logger = logging.getLogger("search_agent_orchestrator")


class SearchAgentOrchestrator(BaseOrchestrator):
    """검색 에이전트 오케스트레이터"""

    def __init__(self):
        super().__init__("search_agent")
        self.logger = logger

        # 검색 노드들 초기화
        self.planning_node = SearchAgentPlanningNode(self.logger)
        self.execution_node = SearchAgentExecutionNode(self.logger)
        self.compression_node = SearchAgentCompressionNode(self.logger)


    def build_workflow(self) -> StateGraph:
        """
        검색 워크플로우를 StateGraph로 구성합니다.
        """
        workflow = StateGraph(SearchState)

        # 1. 노드 정의
        workflow.add_node("plan_search", self.node_plan_search)
        workflow.add_node("execute_tools", self.node_execute_tools)
        workflow.add_node("compress_results", self.node_compress_results)

        # 2. 진입점 정의
        workflow.set_entry_point("plan_search")

        # 3. 엣지 정의 (순차적 실행)
        workflow.add_edge("plan_search", "execute_tools")
        workflow.add_edge("execute_tools", "compress_results")
        workflow.add_edge("compress_results", END)

        return workflow

    def get_entry_point(self) -> str:
        """워크플로우의 진입점 노드명을 반환합니다."""
        return "plan_search"

    def get_state_schema(self):
        """에이전트가 사용하는 상태 스키마를 반환합니다."""
        return SearchState

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """주어진 상태로 에이전트를 실행합니다."""
        try:
            # 워크플로우가 컴파일되지 않았다면 컴파일
            if not self.workflow:
                self.compile_workflow()

            # SearchState로 변환
            search_state = SearchState(**state)

            # 워크플로우 실행
            result = await self.workflow.ainvoke(search_state)

            return result

        except RAIHBusinessException as e:
            self.logger.error("[SEARCH_AGENT_ORCHESTRATOR] 검색 에이전트 실행 실패:  %s", e, exc_info=True)
            raise e

        except Exception as e:
            self.logger.error(
                f"[SEARCH_AGENT_ORCHESTRATOR] 검색 에이전트 실행 실패: {e}"
            )
            return {**state, "error": str(e), "search_completed": False}

    async def node_plan_search(self, state: SearchState) -> Dict[str, Any]:
        """검색 계획 수립 노드"""
        try:
            # 검색 계획 수립 노드 실행
            result = await self.planning_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            return result

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT_ORCHESTRATOR] 검색 계획 수립 실패: {e}")
            return {"available_tools": [], "plan": [], "error": str(e)}

    async def node_execute_tools(self, state: SearchState) -> Dict[str, Any]:
        """검색 도구 실행 노드"""
        try:
            # 검색 도구 실행 노드 실행
            result = await self.execution_node.run_for_langgraph(state)
            # 결과를 상태에 병합
            if result.get('error'):
                result.update({"messages": [
                    AIMessage(content=result.get("error", ""))]})
            state.update(result)
            # 실제 input/output 로그 출력
            tool_results = result.get('tool_results', [])
            for i, tool_result in enumerate(tool_results):
                tool_name = tool_result.get('tool', '')
                raw_result = tool_result.get('raw_result', '')
                formatted_result = tool_result.get('formatted_result', '')
                
                self.logger.info(f"[SEARCH_EXECUTION_INPUT] Tool {i+1}: {tool_name}")
                self.logger.info(f"[SEARCH_EXECUTION_OUTPUT] Tool {i+1} Raw: {str(raw_result)[:500]}...")
                self.logger.info(f"[SEARCH_EXECUTION_OUTPUT] Tool {i+1} Formatted: {str(formatted_result)[:500]}...")

            self.logger.debug(
                f"[SEARCH_AGENT_ORCHESTRATOR] 검색 도구 실행 완료: {len(result.get('tool_results', []))}개 결과"
            )
            return result

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            self.logger.error(f"[SEARCH_AGENT_ORCHESTRATOR] 검색 도구 실행 실패: {e}")
            raise e

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT_ORCHESTRATOR] 검색 도구 실행 실패: {e}")
            return {"tool_results": [], "unified_tool_results": [], "error": str(e)}

    async def node_compress_results(self, state: SearchState) -> Dict[str, Any]:
        """검색 결과 압축 노드"""
        try:
            # 검색 결과 압축 노드 실행
            result = await self.compression_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            return result

        except RAIHBusinessException as e:
            raise e

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT_ORCHESTRATOR] 검색 결과 압축 실패: {e}")
            return {"summary": "", "error": str(e)}

    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보를 반환합니다."""
        return {
            "name": "SearchOrchestrator",
            "description": "검색 에이전트 오케스트레이터 - 완전한 그래프 구조",
            "capabilities": [
                "검색 계획 수립",
                "도구 실행",
                "결과 압축",
                "MCP 도구 통합",
                "실시간 스트리밍",
            ],
            "supported_intents": ["general_question", "search"],
        }
