"""
LLM Knowledge Tool
LLM을 사용하여 지식을 생성하거나 질문에 답변하는 도구
"""

from typing import Any, Dict, List, Optional

from src.agents.components.common.llm_component import LLMComponent
from src.agents.tools.base_tool import BaseTool


class LLMKnowledgeTool(LLMComponent, BaseTool):
    """LLM 지식 도구 - LLM을 사용한 지식 생성"""

    name = "llm_knowledge"
    description = "LLM을 사용하여 복잡한 질문에 답변하거나 지식을 생성합니다."

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__()

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """
        주어진 입력에 대해 LLM을 호출하여 답변을 생성합니다.

        Args:
            tool_input: LLM에 전달할 사용자 질문 또는 프롬프트

        Returns:
            LLM의 응답 결과
        """

        try:
            # LLMComponent의 chat_with_prompt 메서드 사용
            response = await self.chat_with_prompt(
                prompt_template="search_agent/llm_search.j2",
                template_vars={
                    "query": tool_input,
                },
                temperature=0.1,
            )
            return {"response": response.content.strip(), "success": True}

        except Exception as e:
            return {"error": str(e), "success": False}
