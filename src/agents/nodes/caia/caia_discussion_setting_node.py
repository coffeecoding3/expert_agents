"""
CAIA Discussion Setting Node

토론 설정을 수행하고 사용자에게 제시할 메시지를 반환하는 노드
"""

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.discussion.discussion_setup_component import (
    DiscussionSetupComponent,
)
from src.orchestration.states.caia_state import CAIAAgentState

# 허용된 도구 목록 (프론트엔드 query parameter 이름)
ALLOWED_TOOLS = [
    "gemini_web_search",
    "llm_knowledge",
    "internal_knowledge",
]

# 프론트엔드 query parameter 이름 -> 내부 도구 이름 매핑
# 프론트에서 받는 이름과 실제 내부에서 사용하는 이름이 다를 경우 이 매핑을 사용
TOOL_NAME_MAPPING = {
    "web_search": "gemini_web_search",  # 프론트엔드의 web_search는 내부에서 gemini_web_search로 매핑
    "gemini_web_search": "gemini_web_search",
    "llm_knowledge": "llm_knowledge",
    "internal_knowledge": "internal_knowledge",
}


class CAIADiscussionSettingNode:
    """CAIA 토론 설정 노드"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("agents.caia_discussion_setting_node")
        self.setup_component = DiscussionSetupComponent()

    async def run(self, state: CAIAAgentState) -> CAIAAgentState:
        """토론 설정 및 메시지 반환"""
        self.logger.info("[GRAPH][DISCUSSION_SETTING] 토론 설정을 시작합니다")

        query = state.get("user_query", "")
        user_context = state.get("user_context", {})
        chat_history = user_context.get("recent_messages", []) if user_context else []

        # 기존 토론 설정 정보 (수정 요청인 경우)
        existing_topic = state.get("topic")
        existing_speakers = state.get("speakers")

        try:
            # 토론 설정 수행 (기존 설정이 있으면 전달)
            discussion_plan = await self.setup_component.setup_discussion(
                query=query,
                chat_history=chat_history,
                existing_topic=existing_topic,
                existing_speakers=(
                    existing_speakers if isinstance(existing_speakers, list) else None
                ),
            )

            # 결과에서 topic, speakers, message 추출
            topic = discussion_plan.get("topic", "")
            speakers = discussion_plan.get("speakers", [])
            message = discussion_plan.get("message", "")
            discussion_rules = discussion_plan.get("discussion_rules", [])
            token_count = discussion_plan.get("token_count", 0)
            response_second = discussion_plan.get("response_second", 0.0)

            self.logger.info(
                f"[GRAPH][DISCUSSION_SETTING] 토론 설정 완료 - 주제: {topic}, 참여자 수: {len(speakers)}"
            )

            # 도구 목록 추출 및 검증 (discussion_setup_node와 동일한 로직)
            tools = state.get("tools")
            if not tools or not isinstance(tools, list) or len(tools) == 0:
                # 기본값: 모든 도구 활성화
                tools = ALLOWED_TOOLS.copy()
                self.logger.info(
                    "[GRAPH][DISCUSSION_SETTING] 도구 목록이 없어 모든 도구를 활성화합니다."
                )
            else:
                # 유효한 도구만 필터링
                valid_tools = [t for t in tools if t in ALLOWED_TOOLS]
                invalid_tools = [t for t in tools if t not in ALLOWED_TOOLS]
                if invalid_tools:
                    self.logger.warning(
                        f"[GRAPH][DISCUSSION_SETTING] 유효하지 않은 도구가 필터링되었습니다: {invalid_tools}"
                    )
                if not valid_tools:
                    # 유효한 도구가 없으면 모든 도구 활성화
                    valid_tools = ALLOWED_TOOLS.copy()
                    self.logger.warning(
                        "[GRAPH][DISCUSSION_SETTING] 유효한 도구가 없어 모든 도구를 활성화합니다."
                    )
                tools = valid_tools

            # 프론트엔드 이름을 내부 도구 이름으로 매핑
            mapped_tools = [TOOL_NAME_MAPPING.get(t, t) for t in tools]
            self.logger.info(
                f"[GRAPH][DISCUSSION_SETTING] 프론트엔드 도구: {tools} -> 내부 도구: {mapped_tools}"
            )

            # topic, speakers, discussion_rules, tools를 state에 저장 (start_discussion에서 사용)
            return {
                "messages": [AIMessage(content=message)],
                "topic": topic,
                "speakers": speakers,
                "discussion_rules": discussion_rules,
                "tools": mapped_tools,  # 내부 도구 이름으로 저장
                "token_count": token_count,
                "response_second": response_second,
            }

        except Exception as e:
            self.logger.error(
                f"[GRAPH][DISCUSSION_SETTING] 토론 설정 실패: {e}", exc_info=True
            )
            error_message = "토론 설정 중 오류가 발생했습니다. 다시 시도해주세요."
            return {
                "messages": [AIMessage(content=error_message)],
                "topic": None,
                "speakers": [],
            }
