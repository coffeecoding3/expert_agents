"""
CAIA Non-Discussable Component

토론 불가능한 대화를 처리하는 컴포넌트
인사, 감사 등 토론이 불가능한 대화에 대해 간단한 응답을 생성합니다.
"""

from datetime import datetime
from logging import getLogger
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.common.llm_component import LLMComponent
from src.llm.interfaces.chat import ChatMessage, MessageRole
from src.orchestration.states.caia_state import CAIAAgentState
from src.utils.log_collector import collector

logger = getLogger("agents.caia_non_discussable_component")


class CAIANonDiscussableComponent(LLMComponent):
    """CAIA 일반 응답 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    def _build_prompt(self, state: CAIAAgentState) -> str:
        """일반 응답 생성을 위한 프롬프트 구성"""
        from src.prompts.prompt_manager import prompt_manager

        query = state.get("user_query", "")
        user_context = state.get("user_context", {})
        
        # 사용자 메모리 정보
        long_term_memories = user_context.get("long_term_memories", "")
        user_info = long_term_memories

        chat_history = user_context.get("recent_messages", []) if user_context else []

        context: Dict[str, Any] = {
            "query": query,
            "chat_history": chat_history,
            "user_info": user_info,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        return prompt_manager.render_template(
            "caia/caia_non_discussable_response_v1.j2",
            context,
        )

    async def generate_response(self, state: CAIAAgentState) -> Dict[str, Any]:
        """일반 응답 생성"""
        try:
            prompt = self._build_prompt(state)
            logger.info("[NON_DISCUSSABLE] 일반 응답을 생성합니다")
            collector.log("non_discussable_prompt", prompt)

            # LLMComponent의 chat 메서드 사용
            response = await self.chat(
                messages=[ChatMessage(role=MessageRole.USER, content=prompt)],
                temperature=0.1,
            )

            content = getattr(response, "content", str(response))
            logger.info(f"[NON_DISCUSSABLE] 응답 생성 완료: {content[:100]}...")
            collector.log("non_discussable_response", content)

            return {"messages": [AIMessage(content=content)], "success": True}

        except Exception as e:
            logger.error(f"[NON_DISCUSSABLE] 응답 생성 중 오류: {e}")
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ],
                "success": False,
                "error": str(e),
            }
