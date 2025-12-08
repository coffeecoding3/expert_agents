"""
LexAI State Builder

LexAI 에이전트 전용 상태 빌더
"""

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage, HumanMessage

from src.orchestration.common.base_state import AgentStateBuilder
from src.orchestration.states.lexai_state import LexAIAgentState


class LexAIStateBuilder(AgentStateBuilder):
    """LexAI 에이전트 전용 상태 빌더"""

    def create_state(
        self,
        user_query: str = "",
        messages: List[BaseMessage] = None,
        agent_id: int = 3,
        openapi_log_id: str = None,
        old_and_new_no: str = None,
        law_nm: str = None,
        contents: List[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        LexAI 에이전트 상태를 생성합니다.

        Args:
            user_query: 사용자 질의 (법령명으로 사용)
            messages: 메시지 리스트
            agent_id: 에이전트 ID (기본값: 3 - lexai)
            openapi_log_id: OpenAPI 로그 ID
            old_and_new_no: 개정 전후 번호
            law_nm: 법령명
            contents: 법령 개정 내용 목록
            **kwargs: 추가 파라미터

        Returns:
            Dict[str, Any]: 생성된 상태
        """
        # 법령명이 있으면 user_query로 사용
        if law_nm:
            user_query = law_nm

        # 메시지가 없으면 생성
        if messages is None:
            messages = [HumanMessage(content=user_query or law_nm or "법령 분석 요청")]

        # LexAI 전용 상태 생성
        state: LexAIAgentState = {
            "user_query": user_query or law_nm or "",
            "messages": messages,
            "agent_id": agent_id,
            "openapi_log_id": openapi_log_id,
            "old_and_new_no": old_and_new_no,
            "law_nm": law_nm,
            "contents": contents or [],
            "search_query": None,
            "corporate_knowledge": None,
            "advice": None,
        }

        # 추가 파라미터가 있으면 상태에 추가
        for key, value in kwargs.items():
            if key in state:
                state[key] = value

        return state

    def get_state_schema(self) -> type:
        """
        LexAI가 사용하는 상태 스키마를 반환합니다.

        Returns:
            type: LexAIAgentState 클래스
        """
        return LexAIAgentState
