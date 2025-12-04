"""
통합된 에이전트 인터페이스
모든 에이전트가 구현해야 하는 공통 인터페이스를 정의합니다.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional, Type

from src.orchestration.states.caia_state import CAIAAgentState


class BaseAgent(ABC):
    """모든 에이전트의 기본 인터페이스"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    async def run(self, state: CAIAAgentState) -> AsyncGenerator[str, None]:
        """
        에이전트를 실행하고 SSE 스트리밍 응답을 반환합니다.

        Args:
            state: CAIAAgentState 객체

        Yields:
            str: SSE 응답 문자열
        """
        pass

    @abstractmethod
    async def run_for_langgraph(self, state: CAIAAgentState) -> Dict[str, Any]:
        """
        LangGraph용 실행 메서드 (비스트리밍)

        Args:
            state: CAIAAgentState 객체

        Returns:
            Dict[str, Any]: 실행 결과
        """
        pass

    def can_handle_intent(self, intent: str) -> bool:
        """
        해당 의도를 처리할 수 있는지 확인합니다.

        Args:
            intent: 의도 문자열

        Returns:
            bool: 처리 가능 여부
        """
        return intent in self.supported_intents()

    @abstractmethod
    def supported_intents(self) -> list[str]:
        """
        지원하는 의도 목록을 반환합니다.

        Returns:
            list[str]: 지원하는 의도 목록
        """
        pass

    def get_agent_info(self) -> Dict[str, Any]:
        """
        에이전트 정보를 반환합니다.

        Returns:
            Dict[str, Any]: 에이전트 정보
        """
        return {
            "name": self.name,
            "description": self.description,
            "supported_intents": self.supported_intents(),
        }
