"""
Discussion Proceed Component
토론 진행 컴포넌트 - 토론 발화 생성
"""

from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.common.llm_component import LLMComponent
from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.prompts.prompt_manager import prompt_manager
from src.utils.log_collector import collector

logger = getLogger("agents.discussion_proceed_component")


class DiscussionProceedComponent(LLMComponent):
    """토론 진행 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    async def generate_speech(
        self,
        topic: str,
        speaker: str,
        material: List[Dict[str, Any]] = None,
        script: List[Dict[str, Any]] = None,
        discussion_rules: List[str] = [],
        state: Dict[str, Any] = None,
    ) -> str:
        """토론 발화 생성"""

        # ⚠️ 토론 quick테스트용 임시코드
        # flag = state.get("user_query")[-1]
        # if flag in ["2", "3", "4"]:
        #     prompt = f"discussion/generate_speech_v{flag}.j2"
        # else:
        #     prompt = "discussion/generate_speech.j2"  # default
        prompt = "discussion/generate_speech.j2"

        rendered = prompt_manager.render_template(
            prompt,
            {
                "topic": topic,
                "speaker": speaker,
                "materials": material or [],
                "script": script or [],
                "discussion_rules": discussion_rules,
            },
        )
        # collector.log_append("discussion_speech_prompt", rendered) # 너무 길어져서 그냥 log로 맨 마지막꺼만 확인
        collector.log("discussion_speech_prompt", rendered)

        messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

        try:
            # LLMComponent의 chat_with_prompt 메서드 사용
            response = await self.chat(
                messages=messages,
                temperature=0.1,
            )

            # Provider에서 제공하는 response_time과 usage 사용
            response_time = response.response_time or 0.0
            token_count = 0

            # Token 사용량 추적 (state가 있는 경우)
            if state and "total_tokens" in state and response.usage:
                usage = response.usage
                input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
                output_tokens = usage.get("output_tokens") or usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                
                state["total_tokens"]["input_tokens"] += input_tokens
                state["total_tokens"]["output_tokens"] += output_tokens
                state["total_tokens"]["total_tokens"] += total_tokens
                token_count = total_tokens
            elif response.usage:
                # state가 없어도 response에서 직접 가져오기
                usage = response.usage
                token_count = usage.get("total_tokens", 0)

            logger.debug(
                f"Speech generation response for {speaker}: {response.content}"
            )
            
            # provider에서 제공하는 token_count와 response_second를 반환값에 포함 (dict로 반환)
            return {
                "content": response.content.strip(),
                "token_count": token_count,
                "response_second": response_time,
            }

        except Exception as e:
            logger.error(f"Speech generation failed for {speaker}: {e}")
            return {
                "content": f"{speaker}의 발화를 생성할 수 없습니다.",
                "token_count": 0,
                "response_second": 0.0,
            }
