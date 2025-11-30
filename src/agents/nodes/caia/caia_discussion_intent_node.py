"""
CAIA Discussion Intent Node

토론 의도 분석 및 라우팅 노드
"""

import logging
from typing import Any, Dict

from src.agents.components.caia.caia_discussion_intent_analyzer import (
    CAIADiscussionQueryAnalyzer,
    CAIADiscussionIntent,
)
from src.orchestration.states.caia_state import CAIAAgentState
from src.utils.log_collector import collector


class CAIADiscussionIntentNode:
    def __init__(self, logger=None):
        self.query_analyzer = CAIADiscussionQueryAnalyzer()
        self.logger = logger or logging.getLogger("agents.caia_discussion_intent_node")

    async def analyze_query(self, state: CAIAAgentState) -> CAIAAgentState:
        query = state["user_query"]
        user_context = state.get("user_context", {})
        chat_history = user_context.get("recent_messages", []) if user_context else []

        self.logger.info("[GRAPH][INTENT] 토론 의도 분석을 시작합니다")

        analysis = await self.query_analyzer.analyze_intent(
            query=query,
            chat_history=chat_history,
        )

        intent = analysis.get("intent")
        self.logger.info(f"[GRAPH][INTENT] 토론 의도 분석 완료: {intent}")
        collector.log("user_query", query)
        collector.log("chat_history", chat_history)
        collector.log("intent", intent)

        # 의도에 따른 다음 노드 결정
        if intent == CAIADiscussionIntent.SETUP_DISCUSSION.value:
            next_node = "discussion_setting_node"
        elif intent == CAIADiscussionIntent.START_DISCUSSION.value:
            next_node = "discussion"
        elif intent == CAIADiscussionIntent.IS_DISCUSSABLE.value:
            next_node = "discussable_topic_node"
        else:  # NON_DISCUSSABLE
            next_node = "non_discussable_node"

        self.logger.info(f"[GRAPH][INTENT] 다음 노드 결정: {next_node}")

        return {
            "intent": intent,
            "next_node": next_node,
        }

    def route_by_intent(self, state: Dict[str, Any]) -> str:
        next_node = state["next_node"]
        self.logger.info(f"[GRAPH][INTENT] 라우팅: {next_node}")
        return next_node
