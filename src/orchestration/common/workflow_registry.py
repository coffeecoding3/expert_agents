"""
Workflow Registry
에이전트별 워크플로우 등록 및 관리 시스템
"""

import logging
from typing import Dict, Optional, Type

from .base_orchestrator import BaseOrchestrator
from .base_state import AgentStateBuilder

logger = logging.getLogger("workflow_registry")


class WorkflowRegistry:
    """에이전트별 워크플로우 레지스트리"""

    def __init__(self):
        self._orchestrators: Dict[str, BaseOrchestrator] = {}
        self._state_builders: Dict[str, AgentStateBuilder] = {}

    def register_orchestrator(
        self, agent_name: str, orchestrator: BaseOrchestrator
    ) -> None:
        """
        에이전트 오케스트레이터를 등록합니다.

        Args:
            agent_name: 에이전트 이름
            orchestrator: 오케스트레이터 인스턴스
        """
        self._orchestrators[agent_name] = orchestrator
        logger.info(
            f"[WORKFLOW_REGISTRY] {agent_name.upper()} 오케스트레이터 등록 완료"
        )

    def register_state_builder(
        self, agent_name: str, state_builder: AgentStateBuilder
    ) -> None:
        """
        에이전트 상태 빌더를 등록합니다.

        Args:
            agent_name: 에이전트 이름
            state_builder: 상태 빌더 인스턴스
        """
        self._state_builders[agent_name] = state_builder
        logger.info(f"[WORKFLOW_REGISTRY] {agent_name.upper()} 상태 빌더 등록 완료")

    def get_orchestrator(self, agent_name: str) -> Optional[BaseOrchestrator]:
        """
        에이전트의 오케스트레이터를 반환합니다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            BaseOrchestrator: 오케스트레이터 인스턴스, 없으면 None
        """
        return self._orchestrators.get(agent_name)

    def get_state_builder(self, agent_name: str) -> Optional[AgentStateBuilder]:
        """
        에이전트의 상태 빌더를 반환합니다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            AgentStateBuilder: 상태 빌더 인스턴스, 없으면 None
        """
        return self._state_builders.get(agent_name)

    def list_agents(self) -> Dict[str, Dict[str, any]]:
        """
        등록된 에이전트 목록을 반환합니다.

        Returns:
            Dict[str, Dict[str, any]]: 에이전트 정보 딕셔너리
        """
        agents = {}
        for agent_name in self._orchestrators.keys():
            agents[agent_name] = {
                "has_orchestrator": agent_name in self._orchestrators,
                "has_state_builder": agent_name in self._state_builders,
                "entry_point": (
                    self._orchestrators[agent_name].get_entry_point()
                    if agent_name in self._orchestrators
                    else None
                ),
            }
        return agents

    def is_agent_registered(self, agent_name: str) -> bool:
        """
        에이전트가 등록되어 있는지 확인합니다.

        Args:
            agent_name: 에이전트 이름

        Returns:
            bool: 등록 여부
        """
        return agent_name in self._orchestrators

    def get_default_agent(self) -> Optional[str]:
        """
        기본 에이전트 이름을 반환합니다.

        Returns:
            str: 기본 에이전트 이름 (현재는 "caia")
        """
        return "caia" if "caia" in self._orchestrators else None


# 전역 워크플로우 레지스트리 인스턴스
workflow_registry = WorkflowRegistry()
