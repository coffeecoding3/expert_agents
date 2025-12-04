"""
Gemini Web Search Tool
Gemini 기반 웹 검색을 통해 질문에 답변하는 도구
"""

from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.common.gemini_web_search import GeminiWebSearch
from src.agents.tools.base_tool import BaseTool

logger = getLogger("agents.tools.gemini_web_search_tool")

# 웹 검색 결과 형식 타입 정의
WebSearchResult = Dict[
    str, Any
]  # {"search_queries": List[str], "summary": str, "reference": List[str]}


class GeminiWebSearchTool(BaseTool):
    """Gemini 기반 웹 검색 도구 - 외부 시스템 인터페이스"""

    name = "gemini_web_search"
    description = "Gemini 기반 웹 검색을 통해 LLM이 직접 답변하지 못하는 정보를 찾아 질문에 대해 답변합니다."

    def __init__(self):
        """초기화"""
        self.web_search = GeminiWebSearch()

    @staticmethod
    def format_result_as_list(result: WebSearchResult) -> List[WebSearchResult]:
        """
        웹 검색 결과를 리스트 형식으로 변환합니다.

        Args:
            result: 웹 검색 결과 딕셔너리
                   {"search_queries": List[str], "summary": str, "reference": List[str]}

        Returns:
            결과를 포함한 리스트: [{"search_queries": [], "summary": str, "reference": []}]
        """
        if isinstance(result, dict):
            return [
                {
                    "search_queries": result.get("search_queries", []),
                    "summary": result.get("summary", ""),
                    "reference": result.get("reference", []),
                }
            ]
        else:
            # 예상 외 타입인 경우 기본 형식으로 변환
            return [
                {
                    "search_queries": [],
                    "summary": str(result),
                    "reference": [],
                }
            ]

    @staticmethod
    def create_error_result(error_msg: str) -> List[WebSearchResult]:
        """
        에러 결과를 표준 형식으로 생성합니다.

        Args:
            error_msg: 에러 메시지

        Returns:
            에러 결과를 포함한 리스트
        """
        return [
            {
                "search_queries": [],
                "summary": f"웹 검색 중 오류가 발생했습니다: {error_msg}",
                "reference": [],
            }
        ]

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
            f"[GEMINI_WEB_SEARCH_TOOL] 웹 검색 시작: query='{query}'"
        )
        try:
            response = self.web_search.web_search(query=query)
            logger.info(
                f"[GEMINI_WEB_SEARCH_TOOL] 웹 검색 완료. Response type: {type(response)}"
            )
            return {"response": response, "success": True}
        except Exception as e:
            logger.error(f"[GEMINI_WEB_SEARCH_TOOL] 웹 검색 실패: {e}")
            return {"error": str(e), "success": False}
