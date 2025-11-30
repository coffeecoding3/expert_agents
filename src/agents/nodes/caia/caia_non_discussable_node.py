"""
CAIA Non-Discussable Node

토론 불가능한 대화를 처리하는 노드
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.caia.caia_non_discussable_component import (
    CAIANonDiscussableComponent,
)
from src.orchestration.states.caia_state import CAIAAgentState


class CAIANonDiscussableNode:
    """CAIA 일반 응답 노드"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("agents.caia_non_discussable_node")
        self.component = CAIANonDiscussableComponent()

    async def run(self, state: CAIAAgentState) -> CAIAAgentState:
        """일반 응답 생성"""
        self.logger.info("[GRAPH][NON_DISCUSSABLE] 일반 응답 생성을 시작합니다")

        result = await self.component.generate_response(state)

        if result.get("success"):
            self.logger.info("[GRAPH][NON_DISCUSSABLE] 일반 응답 생성 완료")
            return {"messages": result["messages"]}
        else:
            self.logger.error(
                f"[GRAPH][NON_DISCUSSABLE] 응답 생성 실패: {result.get('error')}"
            )
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ]
            }
