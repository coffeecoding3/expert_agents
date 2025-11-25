"""
RAIH State Builder
RAIH 에이전트 전용 상태 빌더
"""

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage

from src.orchestration.common.base_state import AgentStateBuilder
from src.orchestration.states.raih_state import RAIHAgentState


class RAIHStateBuilder(AgentStateBuilder):
    """RAIH 에이전트 전용 상태 빌더"""

    def create_state(
        self,
        user_query: str,
        messages: List[BaseMessage],
        user_id: int = 1,
        actual_user_id: str = None,
        agent_id: int = 1,
        session_id: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        RAIH 에이전트 상태를 생성합니다.
        """
        # 기본값 설정
        actual_user_id = actual_user_id or str(user_id)

        # RAIH 전용 상태 생성
        state: RAIHAgentState = {
            "user_query": user_query,
            "messages": messages,
            "user_id": user_id,
            "actual_user_id": actual_user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "memory": None,
            "intent": None,
            "memory_candidate": None,
            "search_agent_output": None,
            "next_node": "search_agent",
            "user_context": None
        }

        # 추가 파라미터가 있으면 상태에 추가
        for key, value in kwargs.items():
            if key in state:
                state[key] = value

        return state

    def get_state_schema(self) -> type:
        """
        RAIH가 사용하는 상태 스키마를 반환합니다.
        """
        return RAIHAgentState
