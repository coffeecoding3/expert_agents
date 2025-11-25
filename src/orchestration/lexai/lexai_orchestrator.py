"""
LexAI Orchestrator

법령 개정 분석을 위한 오케스트레이터
"""

import logging
from typing import Any, Dict, Type

from langgraph.graph import END, StateGraph

from src.agents.nodes.lexai.lexai_generate_advice_node import LexAIGenerateAdviceNode
from src.agents.nodes.lexai.lexai_generate_search_query_node import (
    LexAIGenerateSearchQueryNode,
)
from src.agents.nodes.lexai.lexai_search_knowledge_node import LexAISearchKnowledgeNode
from src.agents.components import LLMComponent
from src.orchestration.common.base_orchestrator import BaseOrchestrator
from src.orchestration.states.lexai_state import LexAIAgentState

logger = logging.getLogger("lexai_orchestrator")


class LexAIOrchestrator(BaseOrchestrator):
    """
    LangGraph를 사용하여 LexAI 에이전트의 워크플로우를 정의하고 실행하는 오케스트레이터
    """

    def __init__(self):
        super().__init__("lexai")

        # LLM 설정
        llm_config = LLMComponent(agent_code=self.agent_name).get_config()

        # 노드 인스턴스화
        self.generate_search_query_node = LexAIGenerateSearchQueryNode(
            logger=logger, llm_config=llm_config
        )
        self.search_knowledge_node = LexAISearchKnowledgeNode(logger=logger)
        self.generate_advice_node = LexAIGenerateAdviceNode(
            logger=logger, llm_config=llm_config
        )

        # 워크플로우 컴파일
        self.compile_workflow()

    def build_workflow(self) -> StateGraph:
        """
        StateGraph를 사용하여 에이전트 워크플로우를 구성합니다.

        Workflow:
        1. generate_search_query: 법령명과 개정 내용을 분석하여 검색 쿼리 생성
        2. search_corporate_knowledge: 생성된 쿼리로 사내지식 검색
        3. generate_advice: 법령 개정 내용과 사내지식을 기반으로 조언 생성
        """
        workflow = StateGraph(LexAIAgentState)

        # 1. 노드 정의
        workflow.add_node(
            "generate_search_query", self.generate_search_query_node.execute
        )
        workflow.add_node(
            "search_corporate_knowledge", self.search_knowledge_node.execute
        )
        workflow.add_node("generate_advice", self.generate_advice_node.execute)

        # 2. 진입점 정의
        workflow.set_entry_point("generate_search_query")

        # 3. 엣지 정의
        workflow.add_edge("generate_search_query", "search_corporate_knowledge")
        workflow.add_edge("search_corporate_knowledge", "generate_advice")
        workflow.add_edge("generate_advice", END)

        # 4. 워크플로우 반환 (컴파일은 BaseOrchestrator에서 처리)
        return workflow

    async def run(self, state: Dict[str, Any]) -> None:
        """
        주어진 상태로 에이전트를 실행합니다.

        Args:
            state: 에이전트 상태 딕셔너리
        """
        # 기본값 설정
        if not state.get("agent_id"):
            state["agent_id"] = 3  # lexai agent_id (기본값, DB에서 조회 가능)

        # 워크플로우가 컴파일되지 않았다면 컴파일
        if not self.workflow:
            self.compile_workflow()

        # 워크플로우 실행
        async for output in self.workflow.astream(state):
            # 최종 state에 token 정보 포함
            if "total_tokens" in state:
                output["total_tokens"] = state["total_tokens"]
            if "agent_tokens" in state:
                output["agent_tokens"] = state["agent_tokens"]
            pass

    def get_state_schema(self) -> Type:
        """
        LexAI가 사용하는 상태 스키마를 반환합니다.

        Returns:
            Type: LexAIAgentState 클래스
        """
        return LexAIAgentState

    def get_entry_point(self) -> str:
        """
        워크플로우의 진입점 노드명을 반환합니다.

        Returns:
            str: 진입점 노드명
        """
        return "generate_search_query"
