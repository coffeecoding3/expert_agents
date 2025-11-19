"""
CAIA Discussable Topic Component

토론 가능한 주제를 유도하는 컴포넌트
사용자가 토론 가능한 주제를 언급했지만 명확한 토론 요청은 아닌 경우,
토론을 유도하는 응답을 생성합니다.
"""

from logging import getLogger
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.common.llm_component import LLMComponent
from src.llm.interfaces.chat import ChatMessage, MessageRole
from src.orchestration.states.caia_state import CAIAAgentState
from src.utils.log_collector import collector

from pydantic import BaseModel, Field, conlist
import json
from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser

logger = getLogger("agents.caia_discussable_topic_component")


class Message(BaseModel):
    """
    토론 주제 추천 응답 형식 정의
    """

    message: str = Field(..., description="메인 메시지")
    topic_suggestions: conlist(str, min_length=3, max_length=3) = Field(
        ..., description="추천 토론 주제"
    )


class CAIADiscussableTopicComponent(LLMComponent):
    """CAIA 토론 유도 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    def _build_prompt(self, state: CAIAAgentState) -> str:
        """토론 유도 응답 생성을 위한 프롬프트 구성"""
        from src.prompts.prompt_manager import prompt_manager

        query = state.get("user_query", "")
        user_context = state.get("user_context", {})
        chat_history = user_context.get("recent_messages", []) if user_context else []

        # 사용자 메모리 정보
        long_term_memories = user_context.get("long_term_memories", "")
        user_info = long_term_memories

        context: Dict[str, Any] = {
            "query": query,
            "chat_history": chat_history,
            "user_info": user_info,
        }

        return prompt_manager.render_template(
            "caia/caia_discussable_topic_response_v1.j2",
            context,
        )

    async def generate_response(self, state: CAIAAgentState) -> Dict[str, Any]:
        """토론 유도 응답 생성"""
        try:
            prompt = self._build_prompt(state)
            logger.info("[DISCUSSABLE_TOPIC] 토론 유도 응답을 생성합니다")
            collector.log("discussable_topic_prompt", prompt)

            # LLMComponent의 chat 메서드 사용
            response = await self.chat(
                messages=[ChatMessage(role=MessageRole.USER, content=prompt)],
                temperature=0.1,
            )

            content = getattr(response, "content", str(response))

            schema = Message.model_json_schema()
            fallback_response = {"message": "", "topic_suggestions": []}
            json_parser = LLMResponseJsonParser(
                fallback_response=fallback_response, schema=schema
            )
            parsed = json_parser.parse(content)

            logger.info(f"[DISCUSSABLE_TOPIC] 응답 생성 완료: {content[:100]}...")
            collector.log("discussable_topic_response", content)

            return {
                "messages": [AIMessage(content=parsed["message"])],
                "topic_suggestions": parsed["topic_suggestions"],
                "success": True,
            }

        except Exception as e:
            logger.error(f"[DISCUSSABLE_TOPIC] 응답 생성 중 오류: {e}")
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ],
                "topic_suggestions": [],
                "success": False,
                "error": str(e),
            }
