"""
에이전트별 의도 분석 서비스
각 에이전트가 자신만의 의도 분석 로직을 가질 수 있는 서비스
"""

import logging
from typing import Any, Dict

from src.orchestration.states.caia_state import CAIAAgentState

logger = logging.getLogger("agent_intent_service")


class AgentIntentService:
    """에이전트별 의도 분석 서비스"""

    def __init__(self, agent_code: str):
        """
        에이전트별 의도 분석 서비스를 초기화합니다.

        Args:
            agent_code: 에이전트 코드 (caia 등)
        """
        self.agent_code = agent_code
        self.intent_analyzer = self._create_intent_analyzer()

    def _create_intent_analyzer(self):
        """에이전트 코드에 따라 적절한 의도 분석기를 생성합니다."""
        if self.agent_code == "caia":
            from src.agents.components.caia.caia_intent_analyzer import (
                CAIAQueryAnalyzer,
            )

            return CAIAQueryAnalyzer()

        elif self.agent_code == "raih":
            from src.agents.components.raih.raih_intent_analyzer import (
                RAIHQueryAnalyzer,
            )

            return RAIHQueryAnalyzer()
        else:
            # 다른 에이전트들은 기본적으로 일반 의도만 반환
            return None

    async def analyze_intent(self, state) -> Dict[str, Any]:
        """
        에이전트별 의도 분석을 수행합니다.

        Args:
            state: CAIAAgentState 객체

        Returns:
            Dict[str, Any]: 분석 결과
        """
        if not self.intent_analyzer:
            # 의도 분석기가 없는 경우 기본값 반환
            return {
                "intent": "general",
                "next_node": "search_agent",
                "analysis_result": {"intent": "general"},
            }

        logger.info(f"[AGENT_INTENT] {self.agent_code} 의도 분석 시작")

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

            logger.info(f"[AGENT_INTENT] {self.agent_code} 의도 분석 완료: {intent}")

            # 에이전트별 다음 노드 결정
            next_node = self._determine_next_node(intent)

            return {
                "intent": intent,
                "next_node": next_node,
                "analysis_result": analysis_result,
            }
        except Exception as e:
            logger.warning(f"[AGENT_INTENT] {self.agent_code} 의도 분석 실패: {e}")
            return {
                "intent": "general",
                "next_node": "search_agent",
                "analysis_result": {"intent": "general"},
            }

    def _determine_next_node(self, intent: str) -> str:
        """
        에이전트별로 의도에 따라 다음 노드를 결정합니다.

        Args:
            intent: 의도 문자열

        Returns:
            str: 다음 노드 이름
        """
        if self.agent_code == "caia":
            if intent == "discussion":
                return "discussion"
            else:
                return "search_agent"
        else:
            # 다른 에이전트들은 기본적으로 search_agent로 라우팅
            return "search_agent"

    def is_special_intent(self, intent: str) -> bool:
        """
        특수 의도인지 확인합니다.

        Args:
            intent: 의도 문자열

        Returns:
            bool: 특수 의도 여부
        """
        if self.agent_code == "caia":
            return intent == "discussion"
        else:
            return False
