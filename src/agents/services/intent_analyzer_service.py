"""
의도 분석 서비스
사용자 쿼리의 의도를 분석하고 적절한 에이전트를 결정하는 서비스
"""

import logging
from typing import Any, Dict

from src.agents.components.common.intent_analyzer_interface import BaseIntentAnalyzer
from src.agents.services.intent_analyzer_factory import IntentAnalyzerFactory
from src.orchestration.states.caia_state import CAIAAgentState

logger = logging.getLogger("intent_analyzer")


class IntentAnalyzerService:
    """의도 분석 서비스"""

    def __init__(self):
        """
        의도 분석 서비스를 초기화합니다.
        CAIA 전용 의도 분석 서비스입니다.
        """
        self.agent_name = "caia"
        self.intent_analyzer = IntentAnalyzerFactory.create_analyzer("caia")

    async def analyze_intent(self, state: CAIAAgentState) -> Dict[str, Any]:
        """
        사용자 쿼리의 의도를 분석합니다.

        Args:
            state: CAIAAgentState 객체

        Returns:
            Dict[str, Any]: 의도 분석 결과
        """
        logger.info("[INTENT_ANALYZER] CAIA 의도 분석 시작")

        try:
            query = state["user_query"]
            user_context = state.get("user_context", {})
            chat_history = user_context.get("recent_messages", [])

            analysis_result = await self.intent_analyzer.analyze_intent(
                query=query,
                chat_history=chat_history,
                user_context=user_context,
            )
            intent = analysis_result.get("intent")

            logger.info(f"[INTENT_ANALYZER] CAIA 의도 분석 완료: {intent}")

            # CAIA 다음 노드 결정
            next_node = self._determine_next_node(intent)

            return {
                "intent": intent,
                "next_node": next_node,
                "analysis_result": analysis_result,
            }
        except Exception as e:
            logger.warning(f"[INTENT_ANALYZER] CAIA 의도 분석 실패: {e}")
            return {
                "intent": "general",
                "next_node": "search_agent",
                "analysis_result": {"intent": "general"},
            }

    def _determine_next_node(self, intent: str) -> str:
        """
        의도에 따라 다음 노드를 결정합니다.

        Args:
            intent: 의도 문자열

        Returns:
            str: 다음 노드 이름
        """
        if intent == "discussion":
            return "discussion"
        else:
            return "search_agent"

    def is_discussion_intent(self, intent: str) -> bool:
        """
        토론 의도인지 확인합니다.

        Args:
            intent: 의도 문자열

        Returns:
            bool: 토론 의도 여부
        """
        return intent == "discussion"

    def get_supported_intents(self) -> list[str]:
        """
        지원하는 의도 목록을 반환합니다.

        Returns:
            list[str]: 지원하는 의도 목록
        """
        return self.intent_analyzer.get_supported_intents()


# 전역 서비스 인스턴스 (CAIA 전용)
intent_analyzer_service = IntentAnalyzerService()
