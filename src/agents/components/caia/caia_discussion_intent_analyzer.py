"""
CAIA Discussion Intent Analyzer Component

사용자 쿼리 분석 및 토론 의도 분류 컴포넌트
"""

from enum import Enum
from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.common.intent_analyzer_interface import BaseIntentAnalyzer
from src.agents.components.common.llm_component import LLMComponent
from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser
from src.llm.interfaces.chat import ChatMessage, MessageRole
from src.prompts.prompt_manager import prompt_manager
from src.utils.log_collector import collector

logger = getLogger("agents.caia_discussion_intent_analyzer")


class CAIADiscussionIntent(Enum):
    """CAIA 토론 의도 분류"""

    CLEAR_DISCUSSION = "clear_discussion"  # 명확한 토론의도 (예: "ESG경영을 잘하기 위한 방안에 대해 토론해줘")
    IS_DISCUSSABLE = "is_discussable"  # 토론가능한 주제로 유도 가능 (예: "ESG경영")
    NON_DISCUSSABLE = "non_discussable"  # 토론 불가능 (예: "안녕", "고마워")


class CAIADiscussionQueryAnalyzer(LLMComponent, BaseIntentAnalyzer):
    """CAIA 토론 의도 분석 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    async def analyze_intent(
        self,
        query: str,
        chat_history: List[Dict[str, str]] = None,
        user_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """토론 Agent 의도 분석

        Args:
            query: 사용자 쿼리
        Returns:
            분석 결과
        """

        # default fallback 정의
        fallback_response = {"intent": CAIADiscussionIntent.NON_DISCUSSABLE.value}
        json_parser = LLMResponseJsonParser(fallback_response)

        try:
            # 프롬프트 렌더링
            prompt = prompt_manager.render_template(
                "caia/caia_discussion_intent_analysis_v1.j2",
                {"query": query, "chat_history": chat_history or []},
            )
            
            # 완성된 프롬프트를 collector에 저장
            collector.log("discussion_intent_prompt", prompt)
            
            # LLMComponent의 chat 메서드 사용
            response = await self.chat(
                messages=[ChatMessage(role=MessageRole.USER, content=prompt)],
                temperature=0.1,
            )
            # LLMComponent의 chat_with_prompt 메서드 사용
            # response = await self.chat_with_prompt(
            #     prompt_template="caia/caia_discussion_intent_analysis_v1.j2",
            #     template_vars={"query": query, "chat_history": chat_history},
            #     temperature=0.1,
            # )
            
            parsed_data = json_parser.parse(response.content)
            logger.info(f"[CAIA_DISCUSSION_INTENT] 파싱된 데이터: {parsed_data}")

            return parsed_data

        except Exception as e:
            logger.error(f"Discussion intent analysis failed: {e}")
            return {
                "intent": CAIADiscussionIntent.NON_DISCUSSABLE.value,
            }

    def get_supported_intents(self) -> List[str]:
        """지원하는 의도 목록 반환"""
        return [intent.value for intent in CAIADiscussionIntent]

    def get_intent_enum(self) -> CAIADiscussionIntent:
        """의도 열거형을 반환합니다."""
        return CAIADiscussionIntent
