"""
의도 분석기 팩토리
에이전트별로 적절한 의도 분석기를 생성하는 팩토리
"""

from typing import Dict, Type

from src.agents.components.caia.caia_intent_analyzer import CAIAQueryAnalyzer
from src.agents.components.common.intent_analyzer_interface import BaseIntentAnalyzer


class IntentAnalyzerFactory:
    """의도 분석기 팩토리"""

    _analyzers: Dict[str, Type[BaseIntentAnalyzer]] = {
        "caia": CAIAQueryAnalyzer,
    }

    @classmethod
    def create_analyzer(cls, agent_name: str) -> BaseIntentAnalyzer:
        """
        에이전트명에 따라 적절한 의도 분석기를 생성합니다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            BaseIntentAnalyzer: 의도 분석기 인스턴스

        Raises:
            ValueError: 지원하지 않는 에이전트인 경우
        """
        if agent_name not in cls._analyzers:
            raise ValueError(
                f"Unsupported agent: {agent_name}. Available agents: {list(cls._analyzers.keys())}"
            )

        analyzer_class = cls._analyzers[agent_name]
        return analyzer_class()

    @classmethod
    def register_analyzer(
        cls, agent_name: str, analyzer_class: Type[BaseIntentAnalyzer]
    ) -> None:
        """
        새로운 의도 분석기를 등록합니다.

        Args:
            agent_name: 에이전트 이름
            analyzer_class: 의도 분석기 클래스
        """
        cls._analyzers[agent_name] = analyzer_class

    @classmethod
    def get_supported_agents(cls) -> list[str]:
        """
        지원하는 에이전트 목록을 반환합니다.

        Returns:
            list[str]: 지원하는 에이전트 목록
        """
        return list(cls._analyzers.keys())

    @classmethod
    def get_analyzer_info(cls, agent_name: str) -> Dict[str, any]:
        """
        특정 에이전트의 의도 분석기 정보를 반환합니다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            Dict[str, any]: 의도 분석기 정보
        """
        if agent_name not in cls._analyzers:
            return {}

        analyzer = cls.create_analyzer(agent_name)
        return {
            "agent_name": agent_name,
            "supported_intents": analyzer.get_supported_intents(),
            "intent_enum": analyzer.get_intent_enum(),
        }
