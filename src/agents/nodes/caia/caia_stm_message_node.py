"""
CAIA STM Message Node

대화 메시지를 STM(단기 메모리)에 저장하는 전용 노드
"""

from typing import Any, Callable, Dict

from src.agents.nodes.common.base_stm_message_node import BaseSTMMessageNode

logger = None  # Base class에서 logger 사용


class CAIASTMMessageNode(BaseSTMMessageNode):
    """CAIA STM 메시지 저장 노드 - 워크플로우 조정"""

    def _prepare_tool_input(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        CAIA agent의 state에서 tool_input을 준비합니다.
        토론 스크립트와 요약을 포함합니다.

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
        user_query = state.get("user_query", "")
        messages = state.get("messages", [])

        # 토론 스크립트는 script 또는 discussion_script 키에서 가져옴
        discussion_script = state.get("script") or state.get("discussion_script", [])
        summarize_raw = state.get("summarize", "")
        
        # summarize가 딕셔너리나 리스트인 경우 문자열로 변환
        summarize = ""
        if summarize_raw:
            if isinstance(summarize_raw, str):
                summarize = summarize_raw
            elif isinstance(summarize_raw, dict):
                # 딕셔너리에서 message나 content 추출
                message = summarize_raw.get("message")
                if message:
                    if isinstance(message, list) and len(message) > 0:
                        # AIMessage 객체인 경우
                        first_msg = message[0]
                        if hasattr(first_msg, 'content'):
                            summarize = first_msg.content
                        else:
                            summarize = str(first_msg)
                    else:
                        summarize = str(message)
                else:
                    summarize = summarize_raw.get("content", str(summarize_raw))
            elif isinstance(summarize_raw, list) and len(summarize_raw) > 0:
                # 리스트인 경우 첫 번째 항목의 content 추출
                first_item = summarize_raw[0]
                if hasattr(first_item, 'content'):
                    summarize = first_item.content
                else:
                    summarize = str(first_item)
            else:
                summarize = str(summarize_raw) if summarize_raw else ""

        self.logger.info("[GRAPH] 대화 메시지를 저장합니다")

        tool_input = {
            "user_id": user_id,
            "agent_id": agent_id,
            "session_id": session_id,
            "user_query": user_query,
            "messages": messages,
            "discussion_script": discussion_script,
            "script": discussion_script,  # 별칭으로도 제공
            "summarize": summarize,
        }

        return tool_input
