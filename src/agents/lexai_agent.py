"""
LexAI Agent

법령 개정 분석 및 사내 규정 변경 조언 에이전트
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict

from src.agents.base_agent import BaseAgent
from src.orchestration.states.lexai_state import LexAIAgentState

logger = logging.getLogger("lexai_agent")


class LexAIAgent(BaseAgent):
    """LexAI (Law Revision Analysis AI) 에이전트"""

    def __init__(self):
        super().__init__(
            name="lexai", description="법령 개정 분석 및 사내 규정 변경 조언 AI"
        )

    async def run(self, state: LexAIAgentState) -> AsyncGenerator[str, None]:
        """
        LexAI 에이전트를 실행하고 SSE 스트리밍 응답을 반환합니다.

        Note: 실제 실행은 orchestrator가 담당하므로 이 메서드는 사용되지 않습니다.
        BaseAgent의 abstract method 요구사항을 충족하기 위한 최소 구현입니다.

        Args:
            state: LexAIAgentState 객체

        Yields:
            str: SSE 응답 문자열
        """
        logger.debug("[LEXAI_AGENT] LexAI 에이전트 실행 시작")
        yield f"data: {json.dumps({'type': 'info', 'content': 'LexAI 에이전트가 요청을 처리하고 있습니다.'})}\n\n"
        logger.debug("[LEXAI_AGENT] LexAI 에이전트 실행 완료")

    async def run_for_langgraph(self, state: LexAIAgentState) -> Dict[str, Any]:
        """
        LangGraph용 실행 메서드 (비스트리밍)

        Note: 실제 실행은 orchestrator가 담당하므로 이 메서드는 사용되지 않습니다.
        BaseAgent의 abstract method 요구사항을 충족하기 위한 최소 구현입니다.

        Args:
            state: LexAIAgentState 객체

        Returns:
            Dict[str, Any]: 실행 결과
        """
        logger.debug("[LEXAI_AGENT] LexAI LangGraph 실행")
        return {
            "status": "routed",
            "message": "LexAI 에이전트가 요청을 처리합니다.",
        }

    def supported_intents(self) -> list[str]:
        """
        지원하는 의도 목록을 반환합니다.

        LexAI는 intent 기반 라우팅을 사용하지 않으므로 빈 리스트를 반환합니다.

        Returns:
            list[str]: 지원하는 의도 목록 (빈 리스트)
        """
        return []
