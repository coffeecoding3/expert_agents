"""
CAIA (Chief AI Advisor) Agent
C레벨 임원전용 AI 에이전트
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict

from src.agents.base_agent import BaseAgent
from src.orchestration.states.caia_state import CAIAAgentState

logger = logging.getLogger("caia_agent")


class CAIAAgent(BaseAgent):
    """CAIA (Chief AI Advisor) 에이전트"""

    def __init__(self):
        super().__init__(
            name="caia",
            description="C레벨 임원전용 AI 어드바이저->토론 에이전트로 변환(DiscussionAgent)",
        )

    async def run(self, state: CAIAAgentState) -> AsyncGenerator[str, None]:
        """
        CAIA 에이전트를 실행하고 SSE 스트리밍 응답을 반환합니다.

        Args:
            state: CAIAAgentState 객체

        Yields:
            str: SSE 응답 문자열
        """
        logger.debug("[CAIA_AGENT] CAIA 에이전트 실행 시작")

        # CAIA는 메인 에이전트이므로 직접 실행하지 않고 라우팅만 담당
        # 실제 실행은 하위 에이전트들(SearchAgent, DiscussionAgent)이 담당
        yield f"data: {json.dumps({'type': 'info', 'content': 'CAIA 에이전트가 요청을 처리하고 있습니다.'})}\n\n"

        logger.debug("[CAIA_AGENT] CAIA 에이전트 실행 완료")

    async def run_for_langgraph(self, state: CAIAAgentState) -> Dict[str, Any]:
        """
        LangGraph용 실행 메서드 (비스트리밍)

        Args:
            state: CAIAAgentState 객체

        Returns:
            Dict[str, Any]: 실행 결과
        """
        logger.debug("[CAIA_AGENT] CAIA LangGraph 실행")

        # CAIA는 메인 에이전트이므로 라우팅 결과만 반환
        return {
            "status": "routed",
            "message": "CAIA 에이전트가 요청을 적절한 하위 에이전트로 라우팅했습니다.",
        }

    def supported_intents(self) -> list[str]:
        """
        지원하는 의도 목록을 반환합니다.

        Returns:
            list[str]: 지원하는 의도 목록
        """
        return ["general_question", "discussion"]
