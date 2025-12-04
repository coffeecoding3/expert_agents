"""
Search Planning Node
검색 계획 수립 노드
"""

import logging
from typing import Any, Dict

from src.agents.search_agent import SearchAgentWrapper

logger = logging.getLogger("search_planning_node")


class SearchAgentPlanningNode:
    """검색 계획 수립 노드"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("search_planning_node")
        # SearchAgentWrapper는 state에서 agent_id를 가져와서 동적으로 생성
        self._search_agent_cache = {}

    def _get_search_agent(self, agent_id: int = None, agent_code: str = None):
        """agent_id나 agent_code에 따라 SearchAgentWrapper를 가져오거나 생성"""
        cache_key = agent_code or f"agent_{agent_id}"
        if cache_key not in self._search_agent_cache:
            config = {}
            if agent_id:
                config["agent_id"] = agent_id
            if agent_code:
                config["agent_code"] = agent_code
            self._search_agent_cache[cache_key] = SearchAgentWrapper(config=config)
        return self._search_agent_cache[cache_key]

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph용 검색 계획 수립"""
        self.logger.info("[SEARCH_PLANNING] 검색 계획 수립 시작")

        try:
            query = state.get("user_query", "")
            user_context = state.get("user_context", {})

            # agent_id에 따라 agent_code 결정
            agent_id = state.get("agent_id")
            agent_code = "raih" if agent_id == 2 else "caia"
            search_agent = self._get_search_agent(
                agent_id=agent_id, agent_code=agent_code
            )

            # 사용 가능한 도구 준비
            available_tools_meta = await search_agent._prepare_available_tools()

            # Agent에서 사용하는 도구들만 강제 필터링
            if state.get("agent_id") == 2:
                filter_tool_names = {"retrieve_coporate_knowledge", "llm_knowledge"}
                filtered_tools_list = [
                    item
                    for item in available_tools_meta
                    if (
                        item.get("tool_name") in filter_tool_names
                        or item.get("name") in filter_tool_names
                    )
                ]
                available_tools_meta = filtered_tools_list
                self.logger.debug(
                    f"[SEARCH_AGENT] RAIH Agent - {len(available_tools_meta)}개로 도구가 필터링됩니다"
                )
            # 검색 계획 수립
            plan = await search_agent.planner.plan(
                query=query,
                user_context=user_context,
                available_tools=available_tools_meta,
                agent_id=state.get("agent_id"),
            )

            # RAIH default system_codes 지정
            if state.get("agent_id") == 2:
                from src.utils.config_utils import ConfigUtils

                for task in plan:
                    task["args"]["system_codes"] = ConfigUtils.get_raih_system_codes()

            self.logger.info(
                f"[SEARCH_PLANNING] 검색 계획 수립 완료: {len(plan) if plan else 0}개 계획"
            )

            return {
                "available_tools": available_tools_meta,
                "plan": plan or [],
            }

        except Exception as e:
            self.logger.error(f"[SEARCH_PLANNING] 검색 계획 수립 실패: {e}")
            return {
                "available_tools": [],
                "plan": [],
                "error": str(e),
            }
