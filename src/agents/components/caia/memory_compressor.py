from logging import getLogger
from typing import Any, Dict, List, Optional

from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser
from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.components.memory_compressor")


class MemoryCompressor:

    def __init__(self, *, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or "openai"
        self.model = model

    async def compress(self, memory) -> str:

        try:
            prompt = prompt_manager.render_template(
                "caia/caia_memory_compressor.j2",
                {"memory": memory},
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
            logger.error(f"[MEMORY_COMPRESSION] 메모리 압축 실패: {e}")
            return f"# 압축실패\n{memory}"
