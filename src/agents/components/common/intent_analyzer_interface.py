"""
의도 분석기 인터페이스
모든 에이전트의 의도 분석기가 구현해야 하는 공통 인터페이스
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List


class BaseIntentAnalyzer(ABC):
    """모든 의도 분석기의 기본 인터페이스"""

    @abstractmethod
    async def analyze_intent(
        self,
        query: str,
        chat_history: List[Dict[str, str]] = None,
        user_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        사용자 쿼리의 의도를 분석합니다.

        Args:
            query: 사용자 쿼리
            chat_history: 채팅 히스토리
            user_context: 사용자 컨텍스트

        Returns:
            Dict[str, Any]: 의도 분석 결과
        """
        pass

    @abstractmethod
    def get_supported_intents(self) -> List[str]:
        """
        지원하는 의도 목록을 반환합니다.

        Returns:
            List[str]: 지원하는 의도 목록
        """
        pass

    @abstractmethod
    def get_intent_enum(self) -> Enum:
        """
        의도 열거형을 반환합니다.

        Returns:
            Enum: 의도 열거형
        """
        pass

    def is_special_intent(self, intent: str, special_intent_name: str) -> bool:
        """
        특정 의도인지 확인합니다.

        Args:
            intent: 확인할 의도
            special_intent_name: 특수 의도 이름

        Returns:
            bool: 특수 의도 여부
        """
        return intent == special_intent_name
