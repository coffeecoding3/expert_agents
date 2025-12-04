"""
RAIH STM Message Node

대화 메시지를 STM(단기 메모리)에 저장하는 전용 노드
"""

from typing import Any, Callable, Dict

from src.agents.nodes.common.base_stm_message_node import BaseSTMMessageNode

logger = None  # Base class에서 logger 사용


class RAIHSTMMessageNode(BaseSTMMessageNode):
    """RAIH STM 메시지 저장 노드 - 워크플로우 조정"""

    def _prepare_tool_input(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        RAIH agent의 state에서 tool_input을 준비합니다.
        일반 메시지만 처리합니다.

        Args:
            state: 현재 상태

        Returns:
            tool_input 딕셔너리
        """
        user_id = state.get("user_id")
        if not user_id:
            self.logger.warning("[GRAPH] user_id가 없어 STM 저장을 건너뜁니다")
            return {}

        agent_id = state.get("agent_id") or 1
        session_id = state.get("session_id")
        messages = state.get("messages", [])

        self.logger.info("[GRAPH] 대화 메시지를 저장합니다")

        tool_input = {
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "messages": messages,
        }

        return tool_input
