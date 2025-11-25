"""
CAIA Intent Analysis Tool

사용자 쿼리 의도 분석 도구
"""

from logging import getLogger
from typing import Any, Dict

from src.agents.components.caia.caia_intent_analyzer import CAIAQueryAnalyzer
from src.agents.tools.base_tool import BaseTool

logger = getLogger("agents.tools.caia_intent_analysis")


class CAIAIntentAnalysisTool(BaseTool):
    """CAIA 의도 분석 도구 - 컴포넌트를 래핑한 도구"""

    name = "caia_intent_analysis"
    description = "사용자의 쿼리를 분석하여 주된 의도와 추가 정보를 추출합니다."

    def __init__(self):
        """초기화"""
        self.query_analyzer = CAIAQueryAnalyzer()

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """
        CAIA 의도 분석을 실행합니다.

        Args:
            tool_input: 도구 입력 (딕셔너리 형태: {"query": str, "user_context": dict})

        Returns:
            분석 결과
        """
        # 입력 파싱
        if isinstance(tool_input, dict):
            query = tool_input.get("query", "")
            user_context = tool_input.get("user_context")
        else:
            query = str(tool_input)
            user_context = None

        logger.info(f"[CAIA_INTENT_ANALYSIS] CAIA 의도 분석 실행: query={query}")
        return await self.query_analyzer.analyze_intent(query, user_context)

    def _get_input_schema(self) -> Dict[str, Any]:
        """입력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "분석할 사용자 쿼리"},
                "user_context": {
                    "type": "object",
                    "description": "사용자 컨텍스트 정보 (선택사항)",
                },
            },
            "required": ["query"],
        }

    def _get_output_schema(self) -> Dict[str, Any]:
        """출력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "주요 의도 (general_question/discussion)",
                },
                "confidence": {
                    "type": "number",
                    "description": "분석 신뢰도 (0.0-1.0)",
                },
                "secondary_intents": {"type": "array", "description": "보조 의도 목록"},
                "extracted_info": {
                    "type": "object",
                    "description": "의도별 추출된 정보",
                },
            },
        }

    def is_available(self) -> bool:
        """도구 사용 가능 여부"""
        return True  # 항상 사용 가능

    def validate_input(self, tool_input: Any) -> bool:
        """입력 유효성 검사"""
        if isinstance(tool_input, dict):
            query = tool_input.get("query", "")
        else:
            query = str(tool_input)

        if not query or not isinstance(query, str):
            return False

        if len(query.strip()) < 3:
            return False

        return True
