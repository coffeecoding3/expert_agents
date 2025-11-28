"""
Search Result Compressor Component
검색 결과 압축 컴포넌트 - 검색 결과를 요약하여 압축
"""

from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.common.llm_component import LLMComponent

logger = getLogger("agents.search_result_compressor_component")


class SearchResultCompressorComponent(LLMComponent):
    """검색 결과 압축 컴포넌트"""

    def __init__(self, config: Dict[str, Any] = None):
        """초기화"""
        self.config = config or {}
        # config에서 agent_id나 agent_code를 가져오기
        agent_id = self.config.get("agent_id")
        agent_code = self.config.get("agent_code")
        super().__init__(agent_id=agent_id, agent_code=agent_code)

    async def compress(
        self,
        tool_results: List[Any],
        knowledge: str = None,
        user_context: Dict[str, Any] = None,
        query: str = None,
        intent: str = None,
    ) -> str:
        """검색 결과 압축 (출처 정보 보존)"""
        try:
            # 도구 결과에서 출처 정보 추출 및 보존
            enhanced_tool_results = self._enhance_tool_results_with_sources(
                tool_results
            )

            # LLMComponent의 chat_with_prompt 메서드 사용
            response = await self.chat_with_prompt(
                prompt_template="search_agent/search_agent_results_compress_v2.j2",
                template_vars={
                    "tool_results": enhanced_tool_results,
                    "knowledge": knowledge or "",
                    "user_context": user_context or {},
                    "query": query or "",
                    "intent": intent or "",
                },
                temperature=0.1,  # 더 낮은 temperature로 정확성과 완전성 향상
            )

            logger.debug(f"Search result compression response: {response.content}")
            return response.content.strip()

        except Exception as e:
            logger.error(f"Search result compression failed: {e}")
            return "검색 결과를 압축할 수 없습니다."

    def _enhance_tool_results_with_sources(
        self, tool_results: List[Any]
    ) -> List[Dict[str, Any]]:
        """도구 결과에 출처 정보를 강화하여 추가"""
        enhanced_results = []

        for result in tool_results:
            # UnifiedToolResult 객체인 경우 딕셔너리로 변환
            if hasattr(result, "tool_name"):
                # UnifiedToolResult 객체를 딕셔너리로 변환
                enhanced_result = {
                    "tool": result.tool_name,
                    "raw_result": result.raw_result,
                    "formatted_result": result.formatted_result,
                }
            else:
                # 기존 딕셔너리 형태인 경우
                enhanced_result = result.copy() if isinstance(result, dict) else {}

            # 도구별 출처 정보 강화
            tool_name = enhanced_result.get("tool", "")
            raw_result = enhanced_result.get("raw_result", {})
            source_info = []

            if tool_name == "retrieve_coporate_knowledge":
                # 사내지식 도구의 경우 문서 출처 정보 추가
                if isinstance(raw_result, dict) and "documents" in raw_result:
                    documents = raw_result.get("documents", [])

                    for doc in documents:
                        if isinstance(doc, dict):
                            filename = doc.get("filename", "")
                            view_url = doc.get("view_url", "")
                            title = doc.get("title", doc.get("custom_title", ""))

                            if filename or view_url:
                                source_entry = f"📄 {title}"
                                if filename:
                                    source_entry += f" (파일: {filename})"
                                if view_url:
                                    source_entry += f" (링크: {view_url})"
                                source_info.append(source_entry)

            elif tool_name == "get_events":
                # 일정 도구의 경우 이벤트 출처 정보 추가
                if isinstance(raw_result, dict) and "events" in raw_result:
                    events = raw_result.get("events", [])

                    for event in events:
                        if isinstance(event, dict):
                            subject = event.get("subject", "")
                            start_time = event.get("start", {}).get("dateTime", "")
                            location = event.get("location", {}).get("displayName", "")

                            if subject:
                                source_entry = f"📅 {subject}"
                                if start_time:
                                    source_entry += f" ({start_time})"
                                if location:
                                    source_entry += f" - {location}"
                                source_info.append(source_entry)

            elif tool_name == "get_mails":
                # 메일 도구의 경우 메일 출처 정보 추가
                if isinstance(raw_result, dict) and "messages" in raw_result:
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

                            if subject:
                                source_entry = f"📧 {subject}"
                                if sender:
                                    source_entry += f" (발신자: {sender})"
                                if received_time:
                                    source_entry += f" ({received_time})"
                                source_info.append(source_entry)

            # 출처 정보가 있으면 formatted_result에 추가
            if source_info:
                current_formatted = enhanced_result.get("formatted_result", "")
                source_section = "\n\n📚 출처 정보:\n" + "\n".join(source_info)
                enhanced_result["formatted_result"] = current_formatted + source_section

            enhanced_results.append(enhanced_result)

        return enhanced_results
