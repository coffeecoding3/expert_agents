"""
RAIH (Chief AI Advisor) Agent
신뢰성 AI Helper
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict

from src.agents.base_agent import BaseAgent
from src.orchestration.states.raih_state import RAIHAgentState

logger = logging.getLogger("raih_agent")


class RAIHAgent(BaseAgent):
    """RAIH (Reliability AI Helper) 에이전트"""

    def __init__(self):
        super().__init__(name="raih", description="신뢰성 AI Helper")

    async def run(self, state: RAIHAgentState) -> AsyncGenerator[str, None]:
        """
        RAIH 에이전트를 실행하고 SSE 스트리밍 응답을 반환합니다.

        Args:
            state: RAIHAgentState 객체

        Yields:
            str: SSE 응답 문자열
        """
        logger.info("[RAIH_AGENT] RAIH 에이전트 실행 시작")

        # RAIH는 메인 에이전트이므로 직접 실행하지 않고 라우팅만 담당
        yield f"data: {json.dumps({'type': 'info', 'content': 'RAIH 에이전트가 요청을 처리하고 있습니다.'})}\n\n"

        logger.info("[RAIH_AGENT] RAIH 에이전트 실행 완료")

    async def run_for_langgraph(self, state: RAIHAgentState) -> Dict[str, Any]:
        """
        LangGraph용 실행 메서드 (비스트리밍)

        Args:
            state: RAIHAgentState 객체

        Returns:
            Dict[str, Any]: 실행 결과
        """
        logger.info("[RAIH_AGENT] RAIH LangGraph 실행")

        # RAIH는 메인 에이전트이므로 라우팅 결과만 반환
        return {
            "status": "routed",
            "message": "RAIH 에이전트가 요청을 적절한 하위 에이전트로 라우팅했습니다.",
        }

    def supported_intents(self) -> list[str]:
        """
        지원하는 의도 목록을 반환합니다.

        Returns:
            list[str]: 지원하는 의도 목록
        """
        return ["general_question", "create_fmea", "create_pdiagram", "create_alt", "internal_rag"]
