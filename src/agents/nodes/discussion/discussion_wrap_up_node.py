from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.discussion.discussion_message_storage import (
    DiscussionMessageStorage,
)
from src.agents.components.discussion.discussion_service import Discussion
from src.orchestration.states.discussion_state import DiscussionState
from src.schemas.sse_response import SSEResponse
from src.utils.log_collector import collector


class WrapUpDiscussionNode:

    def __init__(self, logger):
        self.logger = logger
        self.discussion = Discussion()
        # 메시지 저장 모듈
        self.message_storage = DiscussionMessageStorage(logger_instance=self.logger)

    async def run(self, state: DiscussionState):
        self.logger.info(
            "[DISCUSSION: 4. wrap_up_start] 토론 요약 시작 - RUN 메서드 실행됨"
        )
        summarize = await self.discussion.wrap_up_discussion(
            topic=state.get("topic", ""),
            script=state.get("script", []),
            state=state,
        )

        self.logger.info(f"[DISCUSSION: 4. wrap up discussion] {summarize}")
        collector.log("discussion_summary", summarize)

        result = ""
        topic_suggestions = []
        token_count = 0
        response_second = 0.0
        
        if summarize.get("success", False):
            result = summarize.get("message", [AIMessage(content="")])[-1].content
            topic_suggestions = summarize.get("topic_suggestions")
            # 실제 LLM 응답에서 나온 token 수와 응답 시간 사용
            token_count = summarize.get("token_count", 0)
            response_second = summarize.get("response_second", 0.0)

        # 요약이 있는 경우 실시간으로 SSE 스트리밍
        if result and result.strip():
            result_data = f"🌟 **Insight**\n \n{result}"
            message_res = {
                "chat_id": state.get("chat_id", ""),
                "message_id": state.get("message_id", ""),
                "user_id": state.get("user_id", "Unknown"),
                "chat_filter": state.get("chat_filter", ""),
                "message_filter": state.get("message_filter", ""),
                "answer": result_data,
                "token_count": token_count,
                "response_second": response_second,
            }

            # topic_suggestions 전송 플래그 (한 번만 전송하기 위해)
            topic_suggestions_sent = False
            
            for i, char in enumerate(result_data):
                is_done = i == len(result_data) - 1
                sse_response = SSEResponse.create_llm(
                    token=char,
                    done=is_done,
                    appendable=False,
                    message_res=message_res,
                )
                yield await sse_response.send()
                
                # 마지막 문자를 전송한 후에만 topic_suggestions 전송 (한 번만)
                if is_done and not topic_suggestions_sent:
                    if topic_suggestions and len(topic_suggestions) > 0:
                        yield await SSEResponse.create_question_suggest(
                            questions=topic_suggestions
                        ).send()
                        topic_suggestions_sent = True
                        self.logger.info(
                            f"[DISCUSSION: 4. wrap_up] topic_suggestions 전송 완료: {len(topic_suggestions)}개"
                        )
            
            # topic_suggestions는 content에 합치지 않고 별도로 처리
            final_message = result_data
            # Wrap-up 메시지를 DB에 저장 (SSE 스트리밍 후 비동기로 저장)
            try:
                await self.message_storage.save_host_wrapup_message(
                    state=state,
                    wrapup_content=final_message,
                    topic_suggestions=topic_suggestions,
                )
            except Exception as e:
                self.logger.error(
                    f"[DISCUSSION: 4. wrap_up] Wrap-up 메시지 저장 중 오류: {e}"
                )
        else:
            # 요약이 없는 경우 에러 메시지 스트리밍
            error_text = "토론 요약을 생성할 수 없습니다.\n"
            sse_response = SSEResponse.create_error(
                error_message=error_text,
            )
            yield await sse_response.send()

        self.logger.info(f"[DISCUSSION: 4. wrap_up_completed] {summarize}")

        state["summarize"] = summarize

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 호환을 위한 메서드 (상태 반환)"""
        self.logger.info("[DISCUSSION: 4. wrap_up_start] 토론 요약 시작")

        # 토론 주제와 스크립트 정보 가져오기
        topic = state.get("topic", "")
        script = state.get("script", [])

        if not topic or not script:
            self.logger.error(
                "[DISCUSSION: 4. wrap_up_failed] 토론 주제 또는 스크립트 정보 없음"
            )
            return {"summarize": ""}

        # 토론 요약
        summarize = await self.discussion.wrap_up_discussion(
            topic=topic,
            script=script,
            state=state,
        )

        self.logger.info(f"[DISCUSSION: 4. wrap_up_completed] {summarize}")

        return {
            "summarize": summarize or "",
        }
