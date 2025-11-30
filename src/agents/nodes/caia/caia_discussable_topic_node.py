"""
CAIA Discussable Topic Node

토론 가능한 주제를 유도하는 노드
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.caia.caia_discussable_topic_component import (
    CAIADiscussableTopicComponent,
)
from src.orchestration.states.caia_state import CAIAAgentState


class CAIADiscussableTopicNode:
    """CAIA 토론 유도 노드"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("agents.caia_discussable_topic_node")
        self.component = CAIADiscussableTopicComponent()

    async def run(self, state: CAIAAgentState) -> CAIAAgentState:
        """토론 유도 응답 생성"""
        self.logger.info("[GRAPH][DISCUSSABLE_TOPIC] 토론 유도 응답 생성을 시작합니다")

        result = await self.component.generate_response(state)

        if result.get("success"):
            self.logger.info("[GRAPH][DISCUSSABLE_TOPIC] 토론 유도 응답 생성 완료")
            return {
                "messages": result["messages"],
                "topic_suggestions": result.get("topic_suggestions", []),  # 추가
            }
        else:
            self.logger.error(
                f"[GRAPH][DISCUSSABLE_TOPIC] 응답 생성 실패: {result.get('error')}"
            )
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ]
            }
