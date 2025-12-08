"""
Base Agent State Interface
에이전트별 독립적인 상태 구조를 지원하는 기본 인터페이스
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class BaseAgentState(TypedDict):
    """
    모든 에이전트 상태의 기본 구조
    """

    # 공통 필드들
    user_query: str
    messages: List[BaseMessage]
    user_id: int
    actual_user_id: str
    agent_id: int
    session_id: str

    # 의도 분석 관련
    intent: Optional[str]
    user_context: Optional[Dict[str, Any]]

    # 에이전트별 확장 가능한 필드들
    agent_specific_data: Optional[Dict[str, Any]]


class AgentStateBuilder(ABC):
    """
    에이전트별 상태 빌더 인터페이스
    """

    @abstractmethod
    def create_state(
        self,
        user_query: str,
        messages: List[BaseMessage],
        user_id: int = 1,
        actual_user_id: str = None,
        agent_id: int = 1,
        session_id: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        에이전트별 상태를 생성합니다.

        Args:
            user_query: 사용자 질의
            messages: 메시지 리스트
            user_id: 사용자 ID
            actual_user_id: 실제 사용자 ID
            agent_id: 에이전트 ID
            session_id: 세션 ID
            **kwargs: 에이전트별 추가 파라미터

        Returns:
            Dict[str, Any]: 생성된 상태
        """
        pass

    @abstractmethod
    def get_state_schema(self) -> type:
        """
        에이전트가 사용하는 상태 스키마를 반환합니다.

        Returns:
            type: 상태 스키마 클래스
        """
        pass

    def get_common_fields(self) -> Dict[str, Any]:
        """
        공통 필드들을 반환합니다.

        Returns:
            Dict[str, Any]: 공통 필드 딕셔너리
        """
        return {
            "user_query": "",
            "messages": [],
            "user_id": 1,
            "actual_user_id": "1",
            "agent_id": 1,
            "session_id": "",
            "intent": None,
            "user_context": None,
            "agent_specific_data": None,
        }
