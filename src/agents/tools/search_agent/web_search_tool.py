"""
Web Search Tool
웹 검색을 통해 질문에 답변하는 도구
"""

from logging import getLogger
from typing import Any, Dict

from src.agents.components.search_agent.web_search import WebSearch
from src.agents.tools.base_tool import BaseTool

logger = getLogger("agents.tools.web_search_tool")


class CAIAWebSearchTool(BaseTool):
    """웹 검색 도구 - 외부 시스템 인터페이스"""

    name = "web_search"
    description = (
        "웹 검색을 통해 LLM이 직접 답변하지 못하는 정보를 찾아 질문에 대해 답변합니다."
    )

    def __init__(self):
        """초기화"""
        self.web_search = WebSearch()

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """
        질문과 관련한 정보를 웹 검색을 통해 찾아오고, 이를 바탕으로 질문에 대해 답변합니다.

        Args:
            tool_input: 도구 입력 (딕셔너리 형태: {"query": str})

        Returns:
            답변 결과
        """
        # 입력 파싱
        if isinstance(tool_input, dict):
            query = tool_input.get("query", "")
        else:
            query = str(tool_input)

        logger.info(
            f"[WEB_SEARCH_TOOL] 웹 검색 시작: query='{query}'"
        )
        try:
            response = self.web_search.web_search(query=query)
            logger.info(
                f"[WEB_SEARCH_TOOL] 웹 검색 완료. Response type: {type(response)}"
            )
            return {"response": response, "success": True}
        except Exception as e:
            logger.error(f"[WEB_SEARCH_TOOL] 웹 검색 실패: {e}")
            return {"error": str(e), "success": False}
