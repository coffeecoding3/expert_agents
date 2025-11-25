"""
CAIA Final Answer Component
최종 답변 생성 컴포넌트 - 검색 결과와 사용자 컨텍스트를 종합하여 최종 답변 생성
"""

from logging import getLogger
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.common.llm_component import LLMComponent
from src.llm.interfaces.chat import ChatMessage, MessageRole
from src.orchestration.states.caia_state import CAIAAgentState
from src.schemas.sse_response import SSEResponse
from src.utils.log_collector import collector
from src.utils.tool_name_mapper import ToolNameMapper

logger = getLogger("agents.caia_final_answer_component")


class CAIAFinalAnswerComponent(LLMComponent):
    """CAIA 최종 답변 생성 컴포넌트"""

    def __init__(self):
        """초기화"""
        super().__init__(agent_code="caia")

    def _build_final_prompt(self, state: CAIAAgentState) -> str:
        """최종 답변 생성을 위한 프롬프트 구성"""
        from src.prompts.prompt_manager import prompt_manager

        # 검색 결과는 직접 state에 병합되어 있음
        summary = state.get("summary", "")
        tool_results = state.get("tool_results", [])
        unified_tool_results = state.get("unified_tool_results", [])

        logger.debug(f"[FINAL_ANSWER] Summary length: {len(summary)}")
        logger.debug(f"[FINAL_ANSWER] Tool results count: {len(tool_results)}")
        logger.debug(
            f"[FINAL_ANSWER] Unified tool results count: {len(unified_tool_results)}"
        )

        # 사용자 쿼리 추출
        query = state.get("user_query")
        user_context = state.get("user_context", {})

        # 대화 이력 포맷팅
        chat_history = user_context.get("recent_messages", [])
        chat_history = str(chat_history)

        # 사용자 메모리 정보
        long_term_memories = user_context.get("long_term_memories", "")
        user_info = long_term_memories

        # 사용자 개인 메모리 정보
        personal_memories = user_context.get("personal_info", "")
        personal_info = personal_memories.get("personal_memories", "")

        # 검색 결과 포맷팅
        documents_parts = []

        if summary:
            documents_parts.append(f"## 검색 요약:\n{summary}")
            logger.debug(f"[FINAL_ANSWER_DEBUG] Added summary to documents")

        # unified_tool_results가 있으면 사용, 없으면 tool_results 사용
        results_to_use = unified_tool_results if unified_tool_results else tool_results

        if results_to_use and isinstance(results_to_use, list):
            documents_parts.append("## 상세 검색 결과:")
            sources_info = []  # 출처 정보 수집

            for i, result in enumerate(results_to_use, 1):
                logger.debug(
                    f"[FINAL_ANSWER_DEBUG] Tool result {i}: {type(result)} - {str(result)[:200]}..."
                )
                if isinstance(result, dict):
                    tool_name = result.get("tool", "unknown")
                    korean_tool_name = ToolNameMapper.get_korean_name(tool_name)
                    formatted_result = result.get("formatted_result", "")
                    raw_result = result.get("raw_result", {})

                    if formatted_result:
                        # 출처 정보 추출
                        source_info = self._extract_source_info(
                            tool_name, raw_result, korean_tool_name
                        )
                        if source_info:
                            sources_info.append(source_info)

                        documents_parts.append(
                            f"### {i}. {korean_tool_name} 결과:\n{formatted_result}"
                        )
                        logger.debug(
                            f"[FINAL_ANSWER_DEBUG] Added tool {i} formatted_result to documents"
                        )

            # 출처 정보가 있으면 별도 섹션으로 추가
            if sources_info:
                documents_parts.append("## 📚 출처 정보:")
                documents_parts.extend(sources_info)
                logger.debug(
                    f"[FINAL_ANSWER_DEBUG] Added {len(sources_info)} sources to documents"
                )

        documents = (
            "\n\n".join(documents_parts) if documents_parts else "검색 결과가 없습니다."
        )

        # 현재 날짜 정보 추가
        from src.utils.timezone_utils import get_current_time_in_timezone

        current_time = get_current_time_in_timezone()
        current_date = current_time.strftime("%Y-%m-%d")

        logger.info("[FINAL_ANSWER] 최종 답변을 생성합니다")
        context: Dict[str, Any] = {
            "user_query": query,
            "chat_history": chat_history,
            "user_info": user_info,
            "personal_info": personal_info,
            "documents": documents,
            "current_date": current_date,
        }

        return prompt_manager.render_template(
            "caia/caia_final_answer_v2.j2",
            context,
        )

    def _extract_source_info(
        self, tool_name: str, raw_result: dict, korean_tool_name: str
    ) -> str:
        """도구별로 출처 정보를 추출합니다"""
        if not isinstance(raw_result, dict):
            return ""

        source_entries = []

        if tool_name == "retrieve_coporate_knowledge":
            # 사내지식 도구의 경우 문서 출처 정보 (제목, 파일명, 링크가 모두 있는 경우만)
            if "documents" in raw_result:
                documents = raw_result.get("documents", [])
                for doc in documents:
                    if isinstance(doc, dict):
                        filename = doc.get("filename", "")
                        view_url = doc.get("view_url", "")
                        title = doc.get("title", doc.get("custom_title", ""))

                        # 제목, 파일명, 링크가 모두 있는 경우만 출처로 추가
                        if title and filename and view_url:
                            source_entry = (
                                f"- 📄 **{title}** (파일: {filename}, 링크: {view_url})"
                            )
                            source_entries.append(source_entry)

        elif tool_name == "get_events":
            # 일정 도구의 경우 이벤트 출처 정보 (제목, 시간, 장소가 모두 있는 경우만)
            if "events" in raw_result:
                events = raw_result.get("events", [])
                for event in events:
                    if isinstance(event, dict):
                        subject = event.get("subject", "")
                        start_time = event.get("start", {}).get("dateTime", "")
                        location = event.get("location", {}).get("displayName", "")

                        # 제목, 시간, 장소가 모두 있는 경우만 출처로 추가
                        if subject and start_time and location:
                            source_entry = (
                                f"- 📅 **{subject}** ({start_time}) - {location}"
                            )
                            source_entries.append(source_entry)

        elif tool_name == "get_mails":
            # 메일 도구의 경우 메일 출처 정보 (제목, 발신자, 수신시간이 모두 있는 경우만)
            if "messages" in raw_result:
                messages = raw_result.get("messages", [])
                for message in messages:
                    if isinstance(message, dict):
                        subject = message.get("subject", "")
                        sender = (
                            message.get("from", {})
                            .get("emailAddress", {})
                            .get("name", "")
                        )
                        received_time = message.get("receivedDateTime", "")

                        # 제목, 발신자, 수신시간이 모두 있는 경우만 출처로 추가
                        if subject and sender and received_time:
                            source_entry = f"- 📧 **{subject}** (발신자: {sender}, {received_time})"
                            source_entries.append(source_entry)

        elif tool_name in ["web_search", "get_web_search_data"]:
            # 웹검색 도구의 경우 웹 출처 정보
            if "results" in raw_result:
                results = raw_result.get("results", [])
                for result in results:
                    if isinstance(result, dict):
                        title = result.get("title", "")
                        url = result.get("url", "")

                        # 제목과 URL이 모두 있는 경우만 출처로 추가
                        if title and url:
                            source_entry = f"- 🌐 **{title}** ({url})"
                            source_entries.append(source_entry)

        # 출처 정보가 있으면 도구명과 함께 반환
        if source_entries:
            return f"### {korean_tool_name} 출처:\n" + "\n".join(source_entries)

        return ""

    async def generate_final_answer(self, state: CAIAAgentState) -> Dict[str, Any]:
        """최종 답변 생성"""
        try:
            # 디버깅: 받은 state 구조 확인
            logger.debug(
                f"[FINAL_ANSWER_DEBUG] Received state keys: {list(state.keys())}"
            )
            logger.debug(
                f"[FINAL_ANSWER_DEBUG] Received state summary: {state.get('summary', 'NOT_FOUND')}"
            )
            logger.debug(
                f"[FINAL_ANSWER_DEBUG] Received state tool_results: {state.get('tool_results', 'NOT_FOUND')}"
            )
            logger.debug(
                f"[FINAL_ANSWER_DEBUG] Received state unified_tool_results: {state.get('unified_tool_results', 'NOT_FOUND')}"
            )

            final_prompt = self._build_final_prompt(state)
            logger.debug(f"[DEBUG] final_prompt: {final_prompt}")

            if final_prompt is None:
                logger.warning("[DEBUG] final_prompt is None")
                return {"error": "프롬프트 생성 실패"}

            # 실제 input/output 로그 출력
            logger.debug(f"[FINAL_ANSWER_INPUT] Prompt: {final_prompt}...")
            collector.log("final_prompt", final_prompt)

            # LLMComponent의 chat 메서드 사용
            response = await self.chat(
                messages=[ChatMessage(role=MessageRole.USER, content=final_prompt)]
            )

            # 실제 output 로그 출력
            logger.debug(f"[FINAL_ANSWER_OUTPUT] Response: {response.content}...")
            collector.log("final_answer", response.content)

            content = getattr(response, "content", str(response))
            return {"messages": [AIMessage(content=content)], "success": True}

        except Exception as e:
            logger.error(f"[GRAPH][7/7] 최종 답변 생성 중 오류: {e}")
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ],
                "success": False,
                "error": str(e),
            }

    async def stream_final_answer(self, state: CAIAAgentState):
        """스트리밍 최종 답변 생성"""
        try:
            final_prompt = self._build_final_prompt(state)
            accumulated_content = ""
            async for response in self.stream_chat(
                messages=[ChatMessage(role=MessageRole.USER, content=final_prompt)]
            ):
                if response.content:
                    accumulated_content += response.content
                    sse_response = SSEResponse.create(
                        token=response.content, done=response.is_complete
                    )
                    yield {
                        "node": "make_final_answer",
                        "type": "llm_stream",
                        "sse_response": sse_response,
                        "content": response.content,
                        "is_complete": response.is_complete,
                        "model": response.model_name,
                    }

            # 최종 메시지 반환
            yield {"messages": [AIMessage(content=accumulated_content)]}

        except Exception as e:
            logger.error(f"[GRAPH][7/7] 최종 답변 스트리밍 중 오류: {e}")
            yield {"node": "make_final_answer", "type": "error", "error": str(e)}
            yield {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ]
            }
