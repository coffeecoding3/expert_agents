import logging
from typing import Any, Dict, List, Optional

from src.agents.components.discussion.discussion_message_storage import (
    DiscussionMessageStorage,
)
from src.agents.components.discussion.discussion_service import Discussion
from src.agents.components.discussion.discussion_utils import (
    DISCUSSION_CONTEXT,
    DISCUSSION_ROLE_HOST,
)
from src.orchestration.states.discussion_state import DiscussionState
from src.schemas.sse_response import SSEResponse
from src.utils.log_collector import collector

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


class SetupDiscussionNode:
    """토론 설정 노드 - 워크플로우 조정"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("agents.discussion_setup_node")
        # Discussion 서비스 사용
        self.discussion_service = Discussion()
        # 메시지 저장 모듈
        self.message_storage = DiscussionMessageStorage(logger_instance=self.logger)

    async def run(self, state: DiscussionState):
        """토론 설정 노드 - SSE 스트리밍과 상태 반환을 모두 지원"""
        self.logger.info(
            "[DISCUSSION: 1. setup_start] 토론 설정 시작 - RUN 메서드 실행됨"
        )

        query = state["user_query"]
        # query = state["messages"][-1].content

        user_context = state.get("user_context", {})
        chat_history = user_context.get("recent_messages", [])

        # Discussion 서비스 사용
        discussion_plan = await self.discussion_service.setup_discussion(
            query=query,
            chat_history=chat_history,
            state=state,
        )

        self.logger.info(f"[DISCUSSION: 1. discussion_plan] {discussion_plan}")
        collector.log("discussion_plan", discussion_plan)

        # 토론 주제와 참가자 정보 추출
        topic = discussion_plan.get("topic", "")
        speakers = discussion_plan.get("speakers", [])
        discussion_rules = discussion_plan.get("discussion_rules", [])
        token_count = discussion_plan.get("token_count", 0)
        response_second = discussion_plan.get("response_second", 0.0)
        
        self.logger.info(
            f"[DISCUSSION: 1. setup] token_count={token_count}, response_second={response_second}"
        )

        # 토론 계획 생성 실패 처리
        if not discussion_plan:
            self.logger.error("[DISCUSSION: 1. setup_failed] 토론 계획 생성 실패")
            error_text = "토론 계획을 생성할 수 없습니다.\n"
            sse_response = SSEResponse.create_error(
                error_message=error_text,
            )
            yield await sse_response.send()

        if not topic or not speakers:
            self.logger.error(
                "[DISCUSSION: 1. setup_failed] 토론 주제 또는 전문가 정보 없음"
            )
            error_text = "토론 주제 또는 전문가 정보를 찾을 수 없습니다.\n"
            sse_response = SSEResponse.create_error(
                error_message=error_text,
            )
            yield await sse_response.send()

        # 토론 시작 발언 스트리밍
        if topic and topic.strip() and speakers and len(speakers) > 0:
            host_script = f"오늘 토론 주제는 '{topic}'입니다.\n"
            host_script += f"이번 토론에서는 {', '.join([s.get('speaker', '') for s in speakers])} 이렇게 {len(speakers)}명을 모셨습니다. 토론을 시작하겠습니다.\n"

            for i, char in enumerate(host_script):
                is_done = i == len(host_script) - 1
                sse_response = SSEResponse.create_multi_llm_streaming(
                    token=char,
                    context=DISCUSSION_CONTEXT,
                    llm_role=DISCUSSION_ROLE_HOST,
                    done=is_done,
                    appendable=False,
                )
                yield await sse_response.send()

            # Setup 메시지를 DB에 저장 (SSE 스트리밍 후 비동기로 저장)
            try:
                await self.message_storage.save_host_setup_message(
                    state=state,
                    host_script=host_script,
                )
            except Exception as e:
                self.logger.error(
                    f"[DISCUSSION: 1. setup] Setup 메시지 저장 중 오류: {e}"
                )
        else:
            # 주제가 없는 경우 에러 메시지 스트리밍
            error_text = "토론 주제를 설정할 수 없습니다.\n"
            sse_response = SSEResponse.create_error(
                error_message=error_text,
            )
            yield await sse_response.send()

        self.logger.info(f"[DISCUSSION: 1. setup_completed] {discussion_plan}")

        # 도구 목록 추출 및 검증
        tools = state.get("tools")
        if not tools or not isinstance(tools, list) or len(tools) == 0:
            # 기본값: 모든 도구 활성화
            tools = ALLOWED_TOOLS.copy()
            self.logger.info(
                "[DISCUSSION: 1. setup] 도구 목록이 없어 모든 도구를 활성화합니다."
            )
        else:
            # 유효한 도구만 필터링
            valid_tools = [t for t in tools if t in ALLOWED_TOOLS]
            invalid_tools = [t for t in tools if t not in ALLOWED_TOOLS]
            if invalid_tools:
                self.logger.warning(
                    f"[DISCUSSION: 1. setup] 유효하지 않은 도구가 필터링되었습니다: {invalid_tools}"
                )
            if not valid_tools:
                # 유효한 도구가 없으면 모든 도구 활성화
                valid_tools = ALLOWED_TOOLS.copy()
                self.logger.warning(
                    "[DISCUSSION: 1. setup] 유효한 도구가 없어 모든 도구를 활성화합니다."
                )
            tools = valid_tools

        # 프론트엔드 이름을 내부 도구 이름으로 매핑
        mapped_tools = [TOOL_NAME_MAPPING.get(t, t) for t in tools]
        self.logger.info(
            f"[DISCUSSION: 1. setup] 프론트엔드 도구: {tools} -> 내부 도구: {mapped_tools}"
        )

        # 상태 업데이트 (내부 도구 이름으로 저장)
        state["topic"] = topic
        state["speakers"] = speakers
        state["discussion_rules"] = discussion_rules
        state["tools"] = mapped_tools
        state["token_count"] = token_count
        state["response_second"] = response_second

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 호환을 위한 메서드 (상태 반환)"""
        self.logger.info("[DISCUSSION: 1. setup_start] 토론 설정 시작")

        # 토론 계획 생성
        messages = state.get("messages", [])
        if messages and len(messages) > 0:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                query = last_message.content
            else:
                query = str(last_message)
        else:
            query = ""
        chat_history = state.get("user_context", {}).get("recent_messages", "")

        # Discussion 서비스 사용
        discussion_plan = await self.discussion_service.setup_discussion(
            query=query,
            chat_history=chat_history,
            state=state,
        )

        if not discussion_plan:
            self.logger.error("[DISCUSSION: 1. setup_failed] 토론 계획 생성 실패")
            return {"topic": "", "speakers": [], "token_count": 0, "response_second": 0.0}

        topic = discussion_plan.get("topic", "")
        speakers = discussion_plan.get("speakers", [])
        discussion_rules = discussion_plan.get("discussion_rules", [])
        token_count = discussion_plan.get("token_count", 0)
        response_second = discussion_plan.get("response_second", 0.0)

        if not topic or not speakers:
            self.logger.error(
                "[DISCUSSION: 1. setup_failed] 토론 주제 또는 전문가 정보 없음"
            )
            return {"topic": "", "speakers": [], "token_count": 0, "response_second": 0.0}

        self.logger.info(
            f"[DISCUSSION: 1. setup_completed] {discussion_plan}, token_count={token_count}, response_second={response_second}"
        )

        # 도구 목록 추출 및 검증
        tools = state.get("tools")
        if not tools or not isinstance(tools, list) or len(tools) == 0:
            # 기본값: 모든 도구 활성화
            tools = ALLOWED_TOOLS.copy()
            self.logger.info(
                "[DISCUSSION: 1. setup] 도구 목록이 없어 모든 도구를 활성화합니다."
            )
        else:
            # 유효한 도구만 필터링
            valid_tools = [t for t in tools if t in ALLOWED_TOOLS]
            invalid_tools = [t for t in tools if t not in ALLOWED_TOOLS]
            if invalid_tools:
                self.logger.warning(
                    f"[DISCUSSION: 1. setup] 유효하지 않은 도구가 필터링되었습니다: {invalid_tools}"
                )
            if not valid_tools:
                # 유효한 도구가 없으면 모든 도구 활성화
                valid_tools = ALLOWED_TOOLS.copy()
                self.logger.warning(
                    "[DISCUSSION: 1. setup] 유효한 도구가 없어 모든 도구를 활성화합니다."
                )
            tools = valid_tools

        # 프론트엔드 이름을 내부 도구 이름으로 매핑
        mapped_tools = [TOOL_NAME_MAPPING.get(t, t) for t in tools]
        self.logger.info(
            f"[DISCUSSION: 1. setup] 프론트엔드 도구: {tools} -> 내부 도구: {mapped_tools}"
        )

        # 도구 목록 추출 및 검증
        tools = state.get("tools")
        if not tools or not isinstance(tools, list) or len(tools) == 0:
            # 기본값: 모든 도구 활성화
            tools = ALLOWED_TOOLS.copy()
            self.logger.info(
                "[DISCUSSION: 1. setup] 도구 목록이 없어 모든 도구를 활성화합니다."
            )
        else:
            # 유효한 도구만 필터링
            valid_tools = [t for t in tools if t in ALLOWED_TOOLS]
            invalid_tools = [t for t in tools if t not in ALLOWED_TOOLS]
            if invalid_tools:
                self.logger.warning(
                    f"[DISCUSSION: 1. setup] 유효하지 않은 도구가 필터링되었습니다: {invalid_tools}"
                )
            if not valid_tools:
                # 유효한 도구가 없으면 모든 도구 활성화
                valid_tools = ALLOWED_TOOLS.copy()
                self.logger.warning(
                    "[DISCUSSION: 1. setup] 유효한 도구가 없어 모든 도구를 활성화합니다."
                )
            tools = valid_tools

        # 프론트엔드 이름을 내부 도구 이름으로 매핑
        mapped_tools = [TOOL_NAME_MAPPING.get(t, t) for t in tools]
        self.logger.info(
            f"[DISCUSSION: 1. setup] 프론트엔드 도구: {tools} -> 내부 도구: {mapped_tools}"
        )

        return {
            "topic": topic,
            "speakers": speakers,
            "discussion_rules": discussion_rules,
            "tools": mapped_tools,  # 내부 도구 이름으로 반환
            "token_count": token_count,
            "response_second": response_second,
        }
