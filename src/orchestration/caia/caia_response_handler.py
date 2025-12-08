"""
CAIA Response Handler
CAIA 에이전트 전용 응답 처리기
"""

import asyncio
from datetime import datetime
from logging import getLogger
from typing import Any, AsyncGenerator, List

from src.orchestration.common.agent_interface import StandardAgentResponseHandler
from src.schemas.sse_response import SSEResponse

logger = getLogger("caia_response_handler")


class CAIAResponseHandler(StandardAgentResponseHandler):
    """CAIA 에이전트 전용 응답 처리기"""

    def __init__(self, logger=None):
        super().__init__(logger=logger or getLogger("caia_response_handler"))
        self.handled_nodes = [
            "analyze_query",  # Intent analysis node (no SSE response needed)
            "make_final_answer",
            "discussion",
            "search_agent",
            "discussable_topic_node",  # Placeholder node (routes to search_agent flow)
            "non_discussable_node",  # Placeholder node (routes to search_agent flow)
            "save_stm_message",
            "extract_and_save_memory",
        ]

    async def handle_response(
        self, node_name: str, node_output: Any
    ) -> AsyncGenerator[str, None]:
        """CAIA 전용 응답 처리"""
        # sse_metadata가 있으면 우선 처리 (부모 클래스의 로직 사용)
        if isinstance(node_output, dict) and "sse_metadata" in node_output:
            async for response in super().handle_response(node_name, node_output):
                yield response
            return

        if node_name == "make_final_answer":
            async for response in self._stream_final_answer(node_output):
                yield response
        elif node_name == "discussion":
            async for response in self._stream_discussion_result(node_output):
                yield response
        elif node_name == "search_agent":
            async for response in self._stream_search_result(node_output):
                yield response
        elif node_name == "discussable_topic_node":
            async for response in self._stream_discussable_topic_result(node_output):
                yield response
        elif node_name == "non_discussable_node":
            async for response in self._stream_non_discussable_result(node_output):
                yield response
        elif node_name in [
            "analyze_query",
            "save_stm_message",
            "save_chat_message",  # 내부 처리 노드 추가
            "sync_lgenie",  # 내부 처리 노드 추가
            "extract_and_save_memory",
        ]:
            # 내부 처리용 노드들은 SSE 응답을 생성하지 않음
            if self.logger:
                self.logger.debug(
                    f"[CAIA_RESPONSE_HANDLER] 내부 처리 노드 '{node_name}' 필터링됨"
                )
            return
        else:
            # 처리되지 않은 노드에 대한 기본 처리
            async for response in self._stream_generic_result(node_output):
                yield response

    async def _stream_final_answer(self, final_output):
        """최종 답변을 스트리밍합니다."""
        content = ""

        if isinstance(final_output, dict):
            messages = final_output.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                # AIMessage 객체에서 content 추출
                if hasattr(last_message, "content"):
                    content = last_message.content
                else:
                    content = str(last_message)
            else:
                # messages가 없는 경우 다른 키 확인
                content = final_output.get("content", str(final_output))
        else:
            # 단순 문자열인 경우
            content = str(final_output)

        if content:
            # 내용을 토큰 단위로 스트리밍
            for char in content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)  # 스트리밍 효과

            # 최종 완료 응답
            yield await SSEResponse.create_llm(
                token=content,  # 전체 응답 내용을 token에 포함
                done=True,
                message_res={
                    "content": content,
                    "role": "assistant",
                    "links": (
                        final_output.get("links", [])
                        if isinstance(final_output, dict)
                        else []
                    ),
                    "images": (
                        final_output.get("images", [])
                        if isinstance(final_output, dict)
                        else []
                    ),
                },
            ).send()

            # Token 사용량 로깅
            if isinstance(final_output, dict) and "total_tokens" in final_output:
                tokens = final_output["total_tokens"]
                self.logger.info(
                    f"[CAIA_TOKEN_USAGE] Total tokens used - "
                    f"Input: {tokens.get('input_tokens', 0)}, "
                    f"Output: {tokens.get('output_tokens', 0)}, "
                    f"Total: {tokens.get('total_tokens', 0)}"
                )

                # 에이전트별 token 사용량 로깅
                if "agent_tokens" in final_output:
                    agent_tokens = final_output["agent_tokens"]
                    for agent_name, agent_token_info in agent_tokens.items():
                        if (
                            agent_token_info.get("total_tokens", 0) > 0
                        ):  # 사용된 token이 있는 경우만 로깅
                            self.logger.info(
                                f"[CAIA_AGENT_TOKEN_USAGE] {agent_name} tokens - "
                                f"Input: {agent_token_info.get('input_tokens', 0)}, "
                                f"Output: {agent_token_info.get('output_tokens', 0)}, "
                                f"Total: {agent_token_info.get('total_tokens', 0)}"
                            )
        else:
            # 내용이 없는 경우
            error_content = "죄송합니다. 응답을 생성할 수 없습니다."
            for char in error_content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            yield await SSEResponse.create_llm(
                token=error_content,  # 전체 에러 내용을 token에 포함
                done=True,
                message_res={
                    "content": error_content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()

    async def _stream_discussion_result(self, discussion_output):
        """토론 결과를 스트리밍합니다."""
        # 토론 결과에서 token 사용량 로깅
        if isinstance(discussion_output, dict) and "total_tokens" in discussion_output:
            tokens = discussion_output["total_tokens"]
            self.logger.info(
                f"[CAIA_DISCUSSION_TOKEN_USAGE] Discussion tokens - "
                f"Input: {tokens.get('input_tokens', 0)}, "
                f"Output: {tokens.get('output_tokens', 0)}, "
                f"Total: {tokens.get('total_tokens', 0)}"
            )

            # 에이전트별 token 사용량 로깅
            if "agent_tokens" in discussion_output:
                agent_tokens = discussion_output["agent_tokens"]
                for agent_name, agent_token_info in agent_tokens.items():
                    if agent_token_info.get("total_tokens", 0) > 0:
                        self.logger.info(
                            f"[CAIA_AGENT_TOKEN_USAGE] {agent_name} tokens - "
                            f"Input: {agent_token_info.get('input_tokens', 0)}, "
                            f"Output: {agent_token_info.get('output_tokens', 0)}, "
                            f"Total: {agent_token_info.get('total_tokens', 0)}"
                        )

        # 토론 결과는 이미 토론 오케스트레이터에서 스트리밍되므로
        # 여기서는 완료 메시지만 전송
        yield await SSEResponse.create_llm(
            token="토론이 완료되었습니다.",
            done=True,
            message_res={
                "content": "토론이 완료되었습니다.",
                "role": "assistant",
                "links": [],
                "images": [],
            },
        ).send()

    async def _stream_search_result(self, search_output):
        """검색 결과를 스트리밍합니다."""
        # 검색 결과에서 token 사용량 로깅
        if isinstance(search_output, dict) and "total_tokens" in search_output:
            tokens = search_output["total_tokens"]
            self.logger.info(
                f"[CAIA_SEARCH_TOKEN_USAGE] Search tokens - "
                f"Input: {tokens.get('input_tokens', 0)}, "
                f"Output: {tokens.get('output_tokens', 0)}, "
                f"Total: {tokens.get('total_tokens', 0)}"
            )

            # 에이전트별 token 사용량 로깅
            if "agent_tokens" in search_output:
                agent_tokens = search_output["agent_tokens"]
                for agent_name, agent_token_info in agent_tokens.items():
                    if agent_token_info.get("total_tokens", 0) > 0:
                        self.logger.info(
                            f"[CAIA_AGENT_TOKEN_USAGE] {agent_name} tokens - "
                            f"Input: {agent_token_info.get('input_tokens', 0)}, "
                            f"Output: {agent_token_info.get('output_tokens', 0)}, "
                            f"Total: {agent_token_info.get('total_tokens', 0)}"
                        )

        # 검색 결과에서 요약 추출
        summary = ""
        if isinstance(search_output, dict):
            summary = search_output.get("summary", "")

        if summary:
            # 검색 결과를 토큰 단위로 스트리밍
            for char in summary:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)  # 스트리밍 효과

            # 최종 완료 응답
            yield await SSEResponse.create_llm(
                token=summary,  # 전체 검색 결과를 token에 포함
                done=True,
                message_res={
                    "content": summary,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()
        else:
            # 검색 결과가 없는 경우
            error_content = "검색 결과를 찾을 수 없습니다."
            for char in error_content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            yield await SSEResponse.create_llm(
                token=error_content,
                done=True,
                message_res={
                    "content": error_content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()

    async def _stream_discussable_topic_result(self, node_output):
        """토론 유도 결과를 스트리밍합니다."""
        from src.schemas.sse_response import MessageResponse

        message = ""
        topic_suggestions = []

        if isinstance(node_output, dict):
            messages = node_output.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    message = last_message.content
                else:
                    message = str(last_message)
            else:
                message = node_output.get("content", "")

            # topic_suggestions 추출
            topic_suggestions = node_output.get("topic_suggestions", [])
        else:
            message = str(node_output)

        # message와 topic_suggestions를 마크다운 형식으로 포맷팅
        if message or topic_suggestions:
            formatted_content = message

            # 포맷팅된 내용을 스트리밍
            for char in formatted_content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            # topic_suggestions를 event_data에 포함하여 전송
            yield await SSEResponse.create_llm(
                token=formatted_content,
                done=True,
                message_res=MessageResponse.from_parameters(
                    content=formatted_content,
                    role="assistant",
                    links=[],
                    images=[],
                    event_data={
                        "topic_suggestions": topic_suggestions,
                    },
                ),
            ).send()

            # topic_suggestions를 QUESTION_SUGGEST 이벤트로 전송
            if topic_suggestions:
                yield await SSEResponse.create_question_suggest(
                    questions=topic_suggestions
                ).send()

        else:
            error_content = "토론 유도 응답을 생성할 수 없습니다."
            yield await SSEResponse.create_llm(
                token=error_content,
                done=True,
                message_res=MessageResponse.from_parameters(
                    content=error_content,
                    role="assistant",
                    links=[],
                    images=[],
                ),
            ).send()

    async def _stream_non_discussable_result(self, node_output):
        """일반 응답 결과를 스트리밍합니다."""
        content = ""
        if isinstance(node_output, dict):
            messages = node_output.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    content = last_message.content
                else:
                    content = str(last_message)
            else:
                content = node_output.get("content", str(node_output))
        else:
            content = str(node_output)

        if content:
            for char in content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            yield await SSEResponse.create_llm(
                token=content,
                done=True,
                message_res={
                    "content": content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()
        else:
            error_content = "응답을 생성할 수 없습니다."
            yield await SSEResponse.create_llm(
                token=error_content,
                done=True,
                message_res={
                    "content": error_content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()

    async def _stream_generic_result(self, node_output):
        """일반적인 노드 결과를 스트리밍합니다."""
        content = self._extract_content(node_output)

        if content:
            for char in content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            yield await SSEResponse.create_llm(
                token=content,
                done=True,
                message_res={
                    "content": content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()
        else:
            error_content = "응답을 생성할 수 없습니다."
            yield await SSEResponse.create_llm(
                token=error_content,
                done=True,
                message_res={
                    "content": error_content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()

    # _extract_content는 StandardAgentResponseHandler에서 상속받아 사용

    def get_handled_nodes(self) -> List[str]:
        """처리 가능한 노드 목록 반환"""
        return self.handled_nodes
