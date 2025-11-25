"""
Discussion Orchestrator
토론 에이전트를 위한 완전한 오케스트레이터
"""

import logging
from typing import Any, Dict, Type

from langgraph.graph import END, StateGraph

from src.agents.nodes.discussion.discussion_get_materials_node import (
    GetDiscussionMaterialsNode,
)
from src.agents.nodes.discussion.discussion_proceed_node import ProceedDiscussionNode
from src.agents.nodes.discussion.discussion_setup_node import SetupDiscussionNode
from src.agents.nodes.discussion.discussion_wrap_up_node import WrapUpDiscussionNode
from src.orchestration.common.base_orchestrator import BaseOrchestrator
from src.orchestration.states.discussion_state import DiscussionState

logger = logging.getLogger("discussion_orchestrator")


class DiscussionOrchestrator(BaseOrchestrator):
    """토론 에이전트 오케스트레이터"""

    def __init__(self):
        super().__init__("discussion")
        self.logger = logger or logging.getLogger("discussion_orchestrator")

        # 토론 노드들 초기화
        self.setup_node = SetupDiscussionNode(self.logger)
        self.materials_node = GetDiscussionMaterialsNode(self.logger)
        self.proceed_node = ProceedDiscussionNode(self.logger)
        self.wrap_up_node = WrapUpDiscussionNode(self.logger)

        self.logger.info("[DISCUSSION_ORCHESTRATOR] 토론 오케스트레이터 초기화 완료")

    def build_workflow(self) -> StateGraph:
        """
        토론 워크플로우를 StateGraph로 구성합니다.
        """
        workflow = StateGraph(DiscussionState)

        # 1. 노드 정의
        workflow.add_node("setup_discussion", self.node_setup_discussion)
        workflow.add_node("get_materials", self.node_get_materials)
        workflow.add_node("proceed_discussion", self.node_proceed_discussion)
        workflow.add_node("wrap_up_discussion", self.node_wrap_up_discussion)

        # 2. 진입점 정의
        workflow.set_entry_point("setup_discussion")

        # 3. 엣지 정의 (순차적 실행)
        workflow.add_edge("setup_discussion", "get_materials")
        workflow.add_edge("get_materials", "proceed_discussion")
        workflow.add_edge("proceed_discussion", "wrap_up_discussion")
        workflow.add_edge("wrap_up_discussion", END)

        return workflow

    async def node_setup_discussion(self, state: DiscussionState) -> Dict[str, Any]:
        """토론 설정 노드"""
        self.logger.debug("[DISCUSSION_ORCHESTRATOR] 토론 설정 노드 실행")

        try:
            # 토론 설정 노드 실행
            result = await self.setup_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            self.logger.debug(
                f"[DISCUSSION_ORCHESTRATOR] 토론 설정 완료: {result.get('topic', '')}"
            )
            return result

        except Exception as e:
            self.logger.error(f"[DISCUSSION_ORCHESTRATOR] 토론 설정 실패: {e}")
            return {"topic": "", "speakers": [], "error": str(e)}

    async def node_get_materials(self, state: DiscussionState) -> Dict[str, Any]:
        """토론 자료 수집 노드"""
        self.logger.debug("[DISCUSSION_ORCHESTRATOR] 자료 수집 노드 실행")

        try:
            # 자료 수집 노드 실행
            result = await self.materials_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            self.logger.debug(
                f"[DISCUSSION_ORCHESTRATOR] 자료 수집 완료: {len(result.get('materials', []))}개"
            )
            return result

        except Exception as e:
            self.logger.error(f"[DISCUSSION_ORCHESTRATOR] 자료 수집 실패: {e}")
            return {"materials": [], "error": str(e)}

    async def node_proceed_discussion(self, state: DiscussionState) -> Dict[str, Any]:
        """토론 진행 노드"""
        self.logger.debug("[DISCUSSION_ORCHESTRATOR] 토론 진행 노드 실행")

        try:
            # 토론 진행 노드 실행
            result = await self.proceed_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            self.logger.debug(
                f"[DISCUSSION_ORCHESTRATOR] 토론 진행 완료: {len(result.get('script', []))}개 발언"
            )
            return result

        except Exception as e:
            self.logger.error(f"[DISCUSSION_ORCHESTRATOR] 토론 진행 실패: {e}")
            return {"script": [], "error": str(e)}

    async def node_wrap_up_discussion(self, state: DiscussionState) -> Dict[str, Any]:
        """토론 요약 노드"""
        self.logger.debug("[DISCUSSION_ORCHESTRATOR] 토론 요약 노드 실행")

        try:
            # 토론 요약 노드 실행
            result = await self.wrap_up_node.run_for_langgraph(state)

            # 결과를 상태에 병합
            state.update(result)

            self.logger.debug("[DISCUSSION_ORCHESTRATOR] 토론 요약 완료")
            return result

        except Exception as e:
            self.logger.error(f"[DISCUSSION_ORCHESTRATOR] 토론 요약 실패: {e}")
            return {"summarize": "", "error": str(e)}

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[override]
        """
        주어진 상태로 토론 에이전트를 실행합니다.

        Args:
            state: 에이전트 상태 딕셔너리

        Returns:
            최종 상태 딕셔너리
        """
        # 기본값 설정
        if not state.get("user_id"):
            state["user_id"] = 1
        if not state.get("agent_id"):
            state["agent_id"] = 1
        if not state.get("actual_user_id"):
            state["actual_user_id"] = str(state.get("user_id", 1))
        if not state.get("session_id"):
            state["session_id"] = ""

        # 워크플로우가 컴파일되지 않았다면 컴파일
        if not self.workflow:
            self.compile_workflow()

        # 워크플로우 실행 및 최종 상태 수집
        final_state = state.copy()
        async for output in self.workflow.astream(state):
            # 각 노드의 출력을 최종 상태에 병합
            for node_name, node_output in output.items():
                if node_output:
                    final_state.update(node_output)

        return final_state

    def get_state_schema(self) -> Type:
        """
        토론 에이전트가 사용하는 상태 스키마를 반환합니다.

        Returns:
            Type: 상태 스키마 클래스
        """
        return DiscussionState

    def get_entry_point(self) -> str:
        """
        워크플로우의 진입점 노드명을 반환합니다.

        Returns:
            str: 진입점 노드명
        """
        return "setup_discussion"

    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보를 반환합니다."""
        return {
            "name": "DiscussionOrchestrator",
            "description": "토론 에이전트 오케스트레이터 - 완전한 그래프 구조",
            "capabilities": [
                "토론 주제 설정",
                "전문가 참가자 선정",
                "참고 자료 수집",
                "실시간 토론 진행",
                "토론 요약 및 결론",
            ],
            "supported_intents": ["discussion"],
        }
