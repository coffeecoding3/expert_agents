# DEPRECATED: Use caia_discussion_intent_node.py instead
# This file is kept for backward compatibility but is no longer used in the CAIA workflow.
# The new caia_discussion_intent_node.py provides 3-way intent classification:
# - clear_discussion: 명확한 토론의도
# - is_discussable: 토론가능한 주제로 유도 가능
# - non_discussable: 토론 불가능한 대화

import logging
from typing import Any, Dict

from src.agents.components.caia.caia_intent_analyzer import (
    CAIAQueryAnalyzer,
    CAIAQueryIntent,
)
from src.orchestration.states.caia_state import CAIAAgentState
from src.utils.log_collector import collector


class IntentNode:
    def __init__(self, logger=None):
        self.query_analyzer = CAIAQueryAnalyzer()
        self.logger = logger or logging.getLogger("agents.intent_node")

    async def analyze_query(self, state: CAIAAgentState) -> CAIAAgentState:
        query = state["user_query"]
        # query = state["messages"][-1].content
        user_context = state.get("user_context", {})
        chat_history = user_context.get("recent_messages", [])

        self.logger.info("[GRAPH][2/7] 의도 분석을 시작합니다")

        analysis = await self.query_analyzer.analyze_intent(
            query=query,
            chat_history=chat_history,
        )

        intent = analysis.get("intent")
        self.logger.info(f"[GRAPH][2/7] 의도 분석 완료: {intent}")
        collector.log("user_query", query)
        collector.log("chat_history", chat_history)
        collector.log("intent", intent)

        # 의도에 따른 다음 노드 결정
        if intent == CAIAQueryIntent.DISCUSSION.value:
            next_node = "discussion"
        else:
            next_node = "search_agent"

        self.logger.info(f"[GRAPH][2/7] 다음 노드 결정: {next_node}")

        return {
            "intent": intent,
            "next_node": next_node,
            # "user_context": user_context,
        }

    def route_by_intent(self, state: Dict[str, Any]) -> str:
        next_node = state["next_node"]
        self.logger.info(f"[GRAPH][2/7] 라우팅: {next_node}")
        return next_node
