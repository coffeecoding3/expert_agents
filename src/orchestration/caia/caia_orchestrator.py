"""
AI 에이전트 오케스트레이션을 위한 메인 진입점
그래프 구동 및 에이전트 실행을 담당하는 메인 모듈
"""

import asyncio
import logging
from typing import Any, Dict, Sequence, Type

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from src.agents.discussion_agent import DiscussionAgent

# 컴포넌트 임포트 (필요한 노드만)
from src.agents.nodes.caia.caia_memory_node import CAIAMemoryNode
from src.agents.nodes.caia.caia_stm_message_node import CAIASTMMessageNode
from src.agents.nodes.caia.caia_chat_message_node import CAIAChatMessageNode
from src.agents.nodes.caia.caia_lgenie_sync_node import CAIALGenieSyncNode
from src.agents.nodes.caia.caia_discussion_intent_node import CAIADiscussionIntentNode
from src.agents.nodes.caia.caia_discussable_topic_node import (
    CAIADiscussableTopicNode,
)
from src.agents.nodes.caia.caia_non_discussable_node import CAIANonDiscussableNode
from src.agents.search_agent import SearchAgentWrapper
from src.llm.manager import llm_manager
from src.memory.memory_manager import memory_manager
from src.orchestration.common.base_orchestrator import BaseOrchestrator
from src.orchestration.states.caia_state import CAIAAgentState
from src.prompts.prompt_manager import prompt_manager

logger = logging.getLogger("graph")


class CAIAOrchestrator(BaseOrchestrator):
    """
    LangGraph를 사용하여 에이전트의 워크플로우를 정의하고 실행하는 오케스트레이터
    """

    def __init__(self):
        super().__init__("caia")
        # 매니저/툴 노드 구성
        self.memory_manager = memory_manager
        self.llm_manager = llm_manager

        # 메모리 매니저 초기화 확인
        if not self.memory_manager.provider:
            logger.warning(
                "메모리 프로바이더가 초기화되지 않았습니다. 메모리 기능이 제한됩니다."
            )
        if not self.memory_manager.stm_provider:
            logger.warning(
                "STM 프로바이더가 초기화되지 않았습니다. 세션 메모리가 제한됩니다."
            )
        # 클래스 기반 노드 인스턴스화 (필요한 노드만)
        self.caia_memory_node = CAIAMemoryNode(
            memory_manager=self.memory_manager,
            logger=logger,
            get_agent_id=self._get_agent_id,
        )
        self.stm_message_node = CAIASTMMessageNode(
            memory_manager=self.memory_manager,
            logger=logger,
            get_agent_id=self._get_agent_id,
        )
        self.chat_message_node = CAIAChatMessageNode(
            logger=logger,
            get_agent_id=self._get_agent_id,
        )
        self.lgenie_sync_node = CAIALGenieSyncNode(logger=logger)
        self.intent_node = CAIADiscussionIntentNode(logger=logger)
        self.discussable_topic_node = CAIADiscussableTopicNode(logger=logger)
        self.non_discussable_node = CAIANonDiscussableNode(logger=logger)
        self.search_agent = SearchAgentWrapper(config={"agent_code": "caia"})
        self.discussion_agent = DiscussionAgent()

        # 노드 메서드 참조
        self.node_analyze_query = self.intent_node.analyze_query
        self.node_extract_and_save_memory = (
            self.caia_memory_node.extract_and_save_memory_new
        )
        self.node_save_stm_message = self.stm_message_node.save_stm_message
        self.node_save_chat_message = self.chat_message_node.save_chat_message
        self.node_sync_lgenie = self.lgenie_sync_node.sync_lgenie
        self.node_search_agent = self._run_search_agent
        self.node_discussion = self._run_discussion_agent
        self.node_discussable_topic = self.discussable_topic_node.run
        self.node_non_discussable = self.non_discussable_node.run

        # 워크플로우 컴파일
        self.compile_workflow()

    async def _run_search_agent(self, state: CAIAAgentState):
        """
        검색 에이전트를 검색 오케스트레이터로 실행합니다.
        """
        try:
            # 검색 오케스트레이터 사용
            from src.orchestration.search_agent.search_agent_orchestrator import (
                SearchAgentOrchestrator,
            )

            search_agent_orchestrator = SearchAgentOrchestrator()

            # CAIAAgentState를 SearchState로 변환
            search_state = {
                **state,
                "available_tools": [],
                "plan": [],
                "tool_results": [],
                "unified_tool_results": [],
                "summary": "",
                "search_completed": False,
            }

            # 검색 워크플로우 실행
            search_result = await search_agent_orchestrator.run(search_state)

            # Token 사용량 추적 (search_result에서 token 정보 추출)
            if "total_tokens" in search_result and "agent_tokens" in state:
                search_tokens = search_result["total_tokens"]
                # search_agent token 정보 업데이트
                state["agent_tokens"]["search_agent"][
                    "input_tokens"
                ] += search_tokens.get("input_tokens", 0)
                state["agent_tokens"]["search_agent"][
                    "output_tokens"
                ] += search_tokens.get("output_tokens", 0)
                state["agent_tokens"]["search_agent"][
                    "total_tokens"
                ] += search_tokens.get("total_tokens", 0)

                # 전체 token 정보 업데이트
                state["total_tokens"]["input_tokens"] += search_tokens.get(
                    "input_tokens", 0
                )
                state["total_tokens"]["output_tokens"] += search_tokens.get(
                    "output_tokens", 0
                )
                state["total_tokens"]["total_tokens"] += search_tokens.get(
                    "total_tokens", 0
                )

                logger.info(
                    f"[CAIA_SEARCH_AGENT_TOKEN] Search Agent tokens - "
                    f"Input: {search_tokens.get('input_tokens', 0)}, "
                    f"Output: {search_tokens.get('output_tokens', 0)}, "
                    f"Total: {search_tokens.get('total_tokens', 0)}"
                )

            # 상태에 검색 결과 추가
            merged_state = {
                **state,
                **search_result,
            }

            return merged_state
        except asyncio.CancelledError:
            logger.warning("[GRAPH] 검색 에이전트 실행이 취소되었습니다.")
            return {
                **state,
                "search_completed": False,
                "error": "검색 에이전트 실행이 취소되었습니다.",
            }
        except Exception as e:
            logger.error(f"[GRAPH] 검색 에이전트 실행 중 오류: {e}")
            return {
                **state,
                "search_completed": False,
                "error": str(e),
            }

    async def _run_discussion_agent(self, state: CAIAAgentState):
        """
        토론 에이전트를 토론 오케스트레이터로 실행합니다.
        """
        try:
            # 토론 오케스트레이터 사용
            from src.orchestration.discussion.discussion_orchestrator import (
                DiscussionOrchestrator,
            )

            discussion_orchestrator = DiscussionOrchestrator()

            # CAIAAgentState를 DiscussionState로 변환
            discussion_state = {
                **state,
                "topic": "",
                "speakers": [],
                "materials": [],
                "script": [],
                "turn_count": 0,
                "summarize": "",
                "discussion_completed": False,
                "tools": state.get("tools"),  # 도구 목록 전달
            }

            # 토론 워크플로우 실행
            discussion_result = await discussion_orchestrator.run(discussion_state)

            # discussion_result가 None인 경우 빈 딕셔너리로 처리
            if discussion_result is None:
                discussion_result = {}

            # Token 사용량 추적 (discussion_result에서 token 정보 추출)
            if (
                discussion_result
                and "total_tokens" in discussion_result
                and "agent_tokens" in state
            ):
                discussion_tokens = discussion_result["total_tokens"]
                # discussion_agent token 정보 업데이트
                state["agent_tokens"]["discussion_agent"][
                    "input_tokens"
                ] += discussion_tokens.get("input_tokens", 0)
                state["agent_tokens"]["discussion_agent"][
                    "output_tokens"
                ] += discussion_tokens.get("output_tokens", 0)
                state["agent_tokens"]["discussion_agent"][
                    "total_tokens"
                ] += discussion_tokens.get("total_tokens", 0)

                # 전체 token 정보 업데이트
                state["total_tokens"]["input_tokens"] += discussion_tokens.get(
                    "input_tokens", 0
                )
                state["total_tokens"]["output_tokens"] += discussion_tokens.get(
                    "output_tokens", 0
                )
                state["total_tokens"]["total_tokens"] += discussion_tokens.get(
                    "total_tokens", 0
                )

                logger.info(
                    f"[CAIA_DISCUSSION_AGENT_TOKEN] Discussion Agent tokens - "
                    f"Input: {discussion_tokens.get('input_tokens', 0)}, "
                    f"Output: {discussion_tokens.get('output_tokens', 0)}, "
                    f"Total: {discussion_tokens.get('total_tokens', 0)}"
                )

            # 상태에 토론 결과 추가
            return {
                **state,
                **discussion_result,
            }
        except asyncio.CancelledError:
            logger.warning("[GRAPH] 토론 에이전트 실행이 취소되었습니다.")
            return {
                **state,
                "discussion_completed": False,
                "error": "토론 에이전트 실행이 취소되었습니다.",
            }
        except Exception as e:
            logger.error(f"[GRAPH] 토론 에이전트 실행 중 오류: {e}")
            return {
                **state,
                "discussion_completed": False,
                "error": str(e),
            }

    def build_workflow(self) -> StateGraph:
        """
        StateGraph를 사용하여 에이전트 워크플로우를 구성합니다.
        """
        workflow = StateGraph(CAIAAgentState)

        # 1. 노드 정의
        workflow.add_node("analyze_query", self.node_analyze_query)
        workflow.add_node("search_agent", self.node_search_agent)
        # discussion 노드는 workflow 밖에서 처리되므로 제거 (SSE 스트리밍을 위해)
        workflow.add_node("discussable_topic_node", self.node_discussable_topic)
        workflow.add_node("non_discussable_node", self.node_non_discussable)
        workflow.add_node("save_stm_message", self.node_save_stm_message)
        workflow.add_node("save_chat_message", self.node_save_chat_message)
        workflow.add_node("sync_lgenie", self.node_sync_lgenie)
        workflow.add_node("extract_and_save_memory", self.node_extract_and_save_memory)

        # 2. 진입점 정의 (의도 분석 노드부터 시작)
        workflow.set_entry_point("analyze_query")

        # 3. 엣지 정의 (의도에 따른 라우팅)
        # discussion은 workflow 밖에서 처리되므로 END로 연결 (chat_generator에서 별도 처리)
        workflow.add_conditional_edges(
            "analyze_query",
            self.intent_node.route_by_intent,
            {
                "discussion": END,  # workflow 밖에서 처리되므로 즉시 종료
                "discussable_topic_node": "discussable_topic_node",
                "non_discussable_node": "non_discussable_node",
            },
        )
        # 모든 경로는 save_stm_message -> save_chat_message -> sync_lgenie -> extract_and_save_memory 순서로 실행
        workflow.add_edge("discussable_topic_node", "save_stm_message")
        workflow.add_edge("non_discussable_node", "save_stm_message")
        workflow.add_edge("search_agent", "save_stm_message")
        workflow.add_edge("save_stm_message", "save_chat_message")
        workflow.add_edge("save_chat_message", "sync_lgenie")
        workflow.add_edge("sync_lgenie", "extract_and_save_memory")
        workflow.add_edge("extract_and_save_memory", END)

        # 4. 워크플로우 반환 (컴파일은 BaseOrchestrator에서 처리)
        return workflow

    def _get_agent_id(self, state: "CAIAAgentState") -> int:
        """상태에서 agent_id를 조회합니다."""
        return state.get("agent_id") or 1

    async def run(self, state: Dict[str, Any]) -> None:
        """
        주어진 상태로 에이전트를 실행합니다.

        Args:
            state: 에이전트 상태 딕셔너리
        """
        # 기본값 설정
        if not state.get("user_id"):
            state["user_id"] = 1
        if not state.get("agent_id"):
            state["agent_id"] = 1
        if not state.get("actual_user_id"):
            state["actual_user_id"] = str(state["user_id"])
        if not state.get("session_id"):
            state["session_id"] = ""

        # 워크플로우가 컴파일되지 않았다면 컴파일
        if not self.workflow:
            self.compile_workflow()

        async for output in self.workflow.astream(state):
            # 최종 state에 token 정보 포함
            if "total_tokens" in state:
                output["total_tokens"] = state["total_tokens"]
            if "agent_tokens" in state:
                output["agent_tokens"] = state["agent_tokens"]
            pass

    def get_state_schema(self) -> Type:
        """
        CAIA가 사용하는 상태 스키마를 반환합니다.
        """
        return CAIAAgentState

    def get_entry_point(self) -> str:
        """
        워크플로우의 진입점 노드명을 반환합니다.
        """
        return "analyze_query"

    async def run_with_params(
        self,
        user_query: str,
        messages: Sequence[BaseMessage],
        user_id: int = None,
        actual_user_id: str = None,
        agent_id: int = None,
        session_id: str = None,
    ):
        """
        파라미터로부터 CAIAAgentState를 생성하여 에이전트를 실행합니다.
        (하위 호환성을 위한 메서드)

        Args:
            messages: 사용자 메시지 시퀀스
            user_id: 데이터베이스 사용자 ID (숫자)
            actual_user_id: 실제 사용자 ID (문자열)
            agent_id: 에이전트 ID
            session_id: 세션 ID
        """
        # 기본값 설정
        user_id = user_id or 1
        agent_id = agent_id or 1

        state: CAIAAgentState = {
            "user_query": user_query,
            "messages": messages,
            "user_id": user_id,
            "actual_user_id": actual_user_id or str(user_id),
            "agent_id": agent_id,
            "session_id": session_id or "",
            "memory": None,
            "intent": None,
            "memory_candidate": None,
            "search_agent_output": None,
            "next_node": "build_user_context",
            "user_context": None,
            "topic": None,
            "speakers": None,
            "materials": None,
            "script": None,
            "summarize": None,
            "discussion_completed": None,
            "total_tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "agent_tokens": {
                "search_agent": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
                "discussion_agent": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            },
        }

        await self.run(state)


async def main():
    """테스트용 메인 함수"""
    if not llm_manager.is_initialized:
        logger.warning(
            "경고: LLM 매니저가 초기화되지 않았습니다. `main.py`를 통해 실행해야 합니다."
        )

    orchestrator = CAIAOrchestrator()

    user_query = "안녕하세요?"
    messages = [HumanMessage(content=user_query)]

    await orchestrator.run_with_params(
        user_query=user_query,
        messages=messages,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
