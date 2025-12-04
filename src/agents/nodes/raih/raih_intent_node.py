import logging
from typing import Any, Dict

from src.agents.components.raih.raih_intent_analyzer import (
    RAIHQueryAnalyzer,
    RAIHQueryIntent,
)
from src.orchestration.states.raih_state import RAIHAgentState
from src.utils.log_collector import collector


class RAIHIntentNode:
    def __init__(self, logger=None):
        self.query_analyzer = RAIHQueryAnalyzer()
        self.logger = logging.getLogger("agents.intent_node")

    async def analyze_query(self, state: RAIHAgentState):
        query = state["user_query"]
        user_context = state.get("user_context", {})
        if user_context is None:
            chat_history = []
        else:
            chat_history = user_context.get("recent_messages", [])

        self.logger.info("의도 분석을 시작합니다")

        analysis = await self.query_analyzer.analyze_intent(
            query=query,
            chat_history=chat_history,
        )

        intent = analysis.get("intent")
        self.logger.info(f"의도 분석 완료: {intent}")
        collector.log("user_query", query)
        collector.log("chat_history", chat_history)
        collector.log("intent", intent)

        # 의도에 따른 다음 노드 결정
        if intent in [RAIHQueryIntent.CREATE_FMEA.value, RAIHQueryIntent.CREATE_PDIAGRAM.value, RAIHQueryIntent.CREATE_ALT.value]:
            next_node = "execute_task"
        else:
            next_node = "llm_knowledge"

        self.logger.info(f"다음 노드 결정: {next_node}")

        return {
            "intent": intent,
            "next_node": next_node
        }

    def route_by_intent(self, state: Dict[str, Any]) -> str:
        next_node = state["next_node"]
        return next_node
