"""
에이전트 레지스트리
의도에 따라 적절한 에이전트를 선택하고 실행하는 중앙 관리 시스템
"""

from typing import Dict, Optional, Type

from src.agents.base_agent import BaseAgent
from src.orchestration.states.caia_state import CAIAAgentState


class AgentRegistry:
    """에이전트 레지스트리 - 의도별 에이전트 관리"""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._intent_to_agent: Dict[str, str] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        """
        에이전트를 레지스트리에 등록합니다.

        Args:
            agent: 등록할 에이전트 인스턴스
        """
        self._agents[agent.name] = agent

        # 의도별 매핑 등록
        for intent in agent.supported_intents():
            if intent in self._intent_to_agent:
                continue
                # raise ValueError(
                #     f"Intent '{intent}' is already registered to agent '{self._intent_to_agent[intent]}'"
                # )
            self._intent_to_agent[intent] = agent.name

    def get_agent_for_intent(self, intent: str) -> Optional[BaseAgent]:
        """
        의도에 맞는 에이전트를 반환합니다.

        Args:
            intent: 의도 문자열

        Returns:
            BaseAgent: 해당 의도를 처리할 수 있는 에이전트, 없으면 None
        """
        agent_name = self._intent_to_agent.get(intent)
        if agent_name:
            return self._agents.get(agent_name)
        return None

    def get_default_agent(self) -> Optional[BaseAgent]:
        """
        기본 에이전트를 반환합니다 (일반적인 검색/답변용).

        Returns:
            BaseAgent: 기본 에이전트
        """
        # "general" 의도를 처리하는 에이전트를 기본으로 사용
        return self.get_agent_for_intent("general")

    def list_agents(self) -> Dict[str, Dict[str, any]]:
        """
        등록된 모든 에이전트 정보를 반환합니다.

        Returns:
            Dict[str, Dict[str, any]]: 에이전트 정보 딕셔너리
        """
        return {name: agent.get_agent_info() for name, agent in self._agents.items()}

    def list_supported_intents(self) -> Dict[str, str]:
        """
        지원하는 모든 의도와 해당 에이전트 매핑을 반환합니다.

        Returns:
            Dict[str, str]: 의도 -> 에이전트명 매핑
        """
        return self._intent_to_agent.copy()


# 전역 레지스트리 인스턴스
agent_registry = AgentRegistry()
