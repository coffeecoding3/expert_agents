"""
Search Agent Planner Component

LLM을 사용해 가용 도구 목록과 사용자 질의/컨텍스트를 바탕으로
실행 가능한 도구 호출 계획을 생성합니다.
"""

from logging import getLogger
from typing import Any, Dict, List, Optional

from src.agents.components.common.llm_component import LLMComponent
from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser

logger = getLogger("agents.search_agent_planner")


class SearchAgentPlanner(LLMComponent):
    """검색 에이전트 플래닝 컴포넌트"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        agent_id: Optional[int] = None,
        agent_code: Optional[str] = None,
    ):
        # config에서 agent_id나 agent_code를 가져오거나 파라미터로 받기
        if config:
            agent_id = agent_id or config.get("agent_id")
            agent_code = agent_code or config.get("agent_code")
        super().__init__(agent_id=agent_id, agent_code=agent_code)

    async def plan(
        self,
        query: str,
        user_context: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
        agent_id: int,
    ) -> List[Dict[str, Any]]:
        """가용 도구에 대한 실행 계획 산출"""
        try:
            # ⚠️ 대화 이력 -> 포맷 확인
            chat_history = user_context.get("recent_messages", "")

            # 현재 날짜 정보 추가
            from src.utils.timezone_utils import get_current_time_in_timezone

            current_time = get_current_time_in_timezone()
            current_date = current_time.strftime("%Y-%m-%d")

            # LLMComponent의 chat_with_prompt 메서드 사용
            response = await self.chat_with_prompt(
                prompt_template=(
                    "search_agent/search_agent_planner_v4.j2"
                ),
                template_vars={
                    "query": query,
                    "chat_history": chat_history,
                    "available_tools": available_tools,
                    "current_date": current_date,
                },
                temperature=0.1,
            )

            # LLMResponseJsonParser 사용
            fallback_response = {"tool_call_plan": []}
            parser = LLMResponseJsonParser(fallback_response=fallback_response)

            try:
                data = parser.parse(response.content)
                plan = data.get("tool_call_plan", [])
                logger.info(f"[PLANNER] 검색 계획 수립 완료: {len(plan)}개")

                normalized: List[Dict[str, Any]] = []
                for step in plan:
                    normalized_step = {
                        "tool": step.get("tool"),
                        "reason": step.get("reason"),
                        "args": step.get("args", {}),
                    }
                    normalized.append(normalized_step)
                return normalized
            except Exception as e:
                logger.error(f"[PLANNER] JSON 파싱 실패: {e}")
                logger.debug(f"[PLANNER] Raw response: {response.content}")
                return []
        except Exception as e:
            logger.warning(f"도구 계획 수립 실패: {e}")
            return []
