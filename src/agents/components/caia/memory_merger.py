from logging import getLogger
from typing import Any, Dict, List, Optional

from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser
from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.components.memory_merger")


class MemoryMerger:

    def __init__(self, *, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or "openai"
        self.model = model

    async def merge(self, user_query, existing_memory, new_information) -> str:
        """
        기존 메모리와 새로운 정보를 병합하여 완전한 메모리를 생성합니다.

        Args:
            user_query: 사용자 질의
            existing_memory: 기존 메모리 내용
            new_information: 새로운 정보

        Returns:
            str: 기존 메모리와 새로운 정보가 병합된 완전한 메모리
        """

        try:
            prompt = prompt_manager.render_template(
                "caia/caia_memory_merger.j2",
                {
                    "user_query": user_query,
                    "existing_memory": existing_memory,
                    "new_information": new_information,
                },
            )

            messages = [
                ChatMessage(role=MessageRole.USER, content=prompt),
            ]

            response = await llm_manager.chat(
                messages=messages,
                provider=self.provider,
                model=self.model,
                temperature=0.0,
            )

            return response.content

        except Exception as e:
            logger.error(f"[MEMORY_MERGE] 메모리 업데이트 실패: {e}")
            return f"# 병합실패\n{existing_memory}\n{new_information}"
