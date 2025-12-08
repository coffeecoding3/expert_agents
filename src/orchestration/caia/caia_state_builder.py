"""
CAIA State Builder
CAIA 에이전트 전용 상태 빌더
"""

from typing import Any, Dict, List

from langchain_core.messages import BaseMessage

from src.orchestration.common.base_state import AgentStateBuilder
from src.orchestration.states.caia_state import CAIAAgentState


class CAIAStateBuilder(AgentStateBuilder):
    """CAIA 에이전트 전용 상태 빌더"""

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
        CAIA 에이전트 상태를 생성합니다.
        """
        # 기본값 설정
        actual_user_id = actual_user_id or str(user_id)

        # CAIA 전용 상태 생성
        state: CAIAAgentState = {
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
            "summary": None,
            "tool_results": None,
            "unified_tool_results": None,
            "next_node": "search_agent",
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

        # 추가 파라미터가 있으면 상태에 추가
        for key, value in kwargs.items():
            if key in state:
                state[key] = value

        return state

    def get_state_schema(self) -> type:
        """
        CAIA가 사용하는 상태 스키마를 반환합니다.
        """
        return CAIAAgentState
