"""
AI 에이전트 오케스트레이션을 위한 메인 진입점
그래프 구동 및 에이전트 실행을 담당하는 메인 모듈
"""

import logging
from typing import Any, Dict, Sequence, Type

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, StateGraph

from src.agents.nodes.raih.raih_execute_task_node import RAIHExecuteTaskNode
from src.agents.nodes.raih.raih_llm_knolwedge_node import RAIHLLMKnowledgeNode
from src.agents.nodes.raih.raih_chat_message_node import RAIHChatMessageNode
from src.agents.nodes.raih.raih_lgenie_sync_node import RAIHLGenieSyncNode
from src.agents.nodes.raih.raih_memory_node import RAIHMemoryNode
from src.agents.nodes.raih.raih_stm_message_node import RAIHSTMMessageNode
from src.agents.nodes.raih.raih_intent_node import RAIHIntentNode
from src.llm.manager import llm_manager
from src.memory.memory_manager import memory_manager
from src.orchestration.common.base_orchestrator import BaseOrchestrator
from src.orchestration.states.raih_state import RAIHAgentState

logger = logging.getLogger("graph")


class RAIHOrchestrator(BaseOrchestrator):
    """
    LangGraph를 사용하여 에이전트의 워크플로우를 정의하고 실행하는 오케스트레이터
    """

    def __init__(self):
        super().__init__("raih")
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
        self.raih_memory_node = RAIHMemoryNode(
            memory_manager=self.memory_manager,
            logger=logger,
            get_agent_id=self._get_agent_id,
        )
        self.stm_message_node = RAIHSTMMessageNode(
            memory_manager=self.memory_manager,
            logger=logger,
            get_agent_id=self._get_agent_id,
        )
        self.intent_node = RAIHIntentNode(
            logger=logger,
        )

        self.chat_message_node = RAIHChatMessageNode(
            logger=logger,
            get_agent_id=self._get_agent_id,
        )

        self.lgenie_sync_node = RAIHLGenieSyncNode(logger=logger)

        from src.agents.components import LLMComponent

        self.llm_knowledge_node = RAIHLLMKnowledgeNode(
            logger=logger,
            llm_config=LLMComponent(agent_code=self.agent_name).get_config(),
        )

        self.execute_task_node = RAIHExecuteTaskNode(
            logger=logger,
            llm_config=LLMComponent(agent_code=self.agent_name).get_config()
        )
        self.node_llm_knowledge = RAIHLLMKnowledgeNode.execute
        self.node_analyze_query = RAIHIntentNode.analyze_query
        self.node_execute_task = RAIHExecuteTaskNode.execute
        self.node_extract_and_save_memory = (
            self.raih_memory_node.extract_and_save_memory_new
        )
        self.node_save_stm_message = self.stm_message_node.save_stm_message
        self.node_save_chat_message = self.chat_message_node.save_chat_message
        self.node_sync_lgenie = self.lgenie_sync_node.sync_lgenie

        # 워크플로우 컴파일
        self.compile_workflow()

    def build_workflow(self) -> StateGraph:
        """
        StateGraph를 사용하여 에이전트 워크플로우를 구성합니다.
        """
        workflow = StateGraph(RAIHAgentState)

        # 1. 노드 정의
        workflow.add_node("analyze_query", self.intent_node.analyze_query)
        workflow.add_node("llm_knowledge", self.llm_knowledge_node.execute)
        workflow.add_node("execute_task", self.execute_task_node.execute)
        workflow.add_node("save_stm_message", self.node_save_stm_message)
        workflow.add_node("save_chat_message", self.node_save_chat_message)
        workflow.add_node("sync_lgenie", self.node_sync_lgenie)
        workflow.add_node("extract_and_save_memory", self.node_extract_and_save_memory)

        # 2. 진입점 정의
        workflow.set_entry_point("analyze_query")

        # 3. 엣지 정의
        workflow.add_conditional_edges(
            "analyze_query",
            self.intent_node.route_by_intent,
            {
                "llm_knowledge": "llm_knowledge",
                "execute_task": "execute_task",
            },
        )
        workflow.add_edge("llm_knowledge", "save_stm_message")
        workflow.add_edge("execute_task", "save_stm_message")
        workflow.add_edge("save_stm_message", "save_chat_message")
        workflow.add_edge("save_chat_message", "sync_lgenie")
        workflow.add_edge("sync_lgenie", "extract_and_save_memory")
        workflow.add_edge("extract_and_save_memory", END)

        # 4. 워크플로우 반환 (컴파일은 BaseOrchestrator에서 처리)
        return workflow

    def _get_agent_id(self, state: "RAIHAgentState") -> int:
        """상태에서 agent_id를 조회합니다."""
        return state.get("agent_id") or 2

    async def run(self, state: Dict[str, Any]) -> None:
        """
        주어진 상태로 에이전트를 실행합니다.

        Args:
            state: 에이전트 상태 딕셔너리
        """
        # 기본값 설정
        # todo 사용자 user_id에 맞게 추후 수정 필요
        if not state.get("user_id"):
            state["user_id"] = 1
        if not state.get("agent_id"):
            state["agent_id"] = 2
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
        RAIH가 사용하는 상태 스키마를 반환합니다.
        """
        return RAIHAgentState

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
        파라미터로부터 RAIHAgentState를 생성하여 에이전트를 실행합니다.
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

        state: RAIHAgentState = {
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
        }

        await self.run(state)


async def main():
    """테스트용 메인 함수"""
    if not llm_manager.is_initialized:
        logger.warning(
            "경고: LLM 매니저가 초기화되지 않았습니다. `main.py`를 통해 실행해야 합니다."
        )

    orchestrator = RAIHOrchestrator()

    user_query = (
        "팬모터 고장 모드와 고장 메커니즘을 나열하고, 고장 모드별 FMEA 작성해줘"
    )
    messages = [HumanMessage(content=user_query)]

    await orchestrator.run_with_params(
        user_query=user_query,
        messages=messages,
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
