"""
CAIA Intent Analyzer Component

사용자 쿼리 분석 및 의도 분류 컴포넌트
"""

from enum import Enum
from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.common.intent_analyzer_interface import BaseIntentAnalyzer
from src.agents.components.common.llm_component import LLMComponent
from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser

logger = getLogger("agents.caia_intent_analyzer")


class CAIAQueryIntent(Enum):
    """CAIA 쿼리 의도 분류"""

    GENERAL_QUESTION = "general_question"  # 일반질문
    DISCUSSION = "discussion"  # 토론


class CAIAQueryAnalyzer(LLMComponent, BaseIntentAnalyzer):
    """CAIA 쿼리 분석 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    async def analyze_intent(
        self,
        query: str,
        chat_history: List[Dict[str, str]] = None,
        user_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """CAIA 쿼리 의도 분석

        Args:
            query: 사용자 쿼리
            user_context: 사용자 컨텍스트
        Returns:
            분석 결과
        """

        # default fallback 정의
        fallback_response = {"intent": CAIAQueryIntent.GENERAL_QUESTION.value}
        json_parser = LLMResponseJsonParser(fallback_response)

        try:
            # LLMComponent의 chat_with_prompt 메서드 사용
            response = await self.chat_with_prompt(
                prompt_template="caia/caia_intent_analysis_v2.j2",
                template_vars={
                    "query": query,
                    "chat_history": chat_history,
                },
                temperature=0.1,
            )
            parsed_data = json_parser.parse(response.content)
            logger.info(f"[CAIA_INTENT] 파싱된 데이터: {parsed_data}")

            return parsed_data

        except Exception as e:
            logger.error(f"Query intent analysis failed: {e}")
            return {
                "intent": CAIAQueryIntent.GENERAL_QUESTION.value,
            }

    def get_supported_intents(self) -> List[str]:
        """지원하는 의도 목록 반환"""
        return [intent.value for intent in CAIAQueryIntent]

    def get_intent_enum(self) -> CAIAQueryIntent:
        """의도 열거형을 반환합니다."""
        return CAIAQueryIntent
