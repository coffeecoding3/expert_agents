"""
RAIH Response Handler
RAIH 에이전트 전용 응답 처리기
"""

import asyncio
from logging import getLogger
from typing import Any, AsyncGenerator, List

from src.orchestration.common.agent_interface import AgentResponseHandler
from src.schemas.sse_response import SSEResponse

logger = getLogger("raih_response_handler")


class RAIHResponseHandler(AgentResponseHandler):
    """RAIH 에이전트 전용 응답 처리기"""

    def __init__(self, logger=None):
        self.logger = logger or getLogger("RAIH_response_handler")
        self.handled_nodes = [
            "search_agent",
            "execute_task",
            "save_stm_message",
            "extract_and_save_memory",
        ]

    async def handle_response(
        self, node_name: str, node_output: Any
    ) -> AsyncGenerator[str, None]:
        """RAIH 전용 응답 처리"""
        # 내부 처리 노드는 SSE 응답을 생성하지 않음
        internal_nodes = {
            "save_stm_message",
            "save_chat_message",
            "sync_lgenie",
            "extract_and_save_memory",
            "analyze_query",
        }
        if node_name in internal_nodes:
            if self.logger:
                self.logger.debug(
                    f"[RAIH_RESPONSE_HANDLER] 내부 처리 노드 '{node_name}' 필터링됨"
                )
            return

        if node_name == "search_agent":
            async for response in self._stream_search_result(node_output):
                yield response
        elif node_name == "execute_task":
            async for response in self._stream_generic_result(node_output):
                yield response
        else:
            # 처리되지 않은 노드에 대한 기본 처리
            if self.logger:
                self.logger.debug(
                    f"[RAIH_RESPONSE_HANDLER] 처리되지 않은 노드: {node_name}"
                )
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
                    f"[RAIH_TOKEN_USAGE] Total tokens used - "
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
                                f"[RAIH_AGENT_TOKEN_USAGE] {agent_name} tokens - "
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

    async def _stream_search_result(self, search_output):
        """검색 결과를 스트리밍합니다."""
        # 검색 결과에서 token 사용량 로깅
        if isinstance(search_output, dict) and "total_tokens" in search_output:
            tokens = search_output["total_tokens"]
            self.logger.info(
                f"[RAIH_SEARCH_TOKEN_USAGE] Search tokens - "
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
                            f"[RAIH_AGENT_TOKEN_USAGE] {agent_name} tokens - "
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

    def _extract_content(self, node_output: Any) -> str:
        """노드 출력에서 내용 추출"""
        if isinstance(node_output, dict):
            # 일반적인 키들에서 내용 추출
            for key in ["content", "summary", "result", "output", "response"]:
                if key in node_output and node_output[key]:
                    return str(node_output[key])

            # messages 배열에서 내용 추출
            if "messages" in node_output and node_output["messages"]:
                messages = node_output["messages"]
                if messages and len(messages) > 0:
                    last_message = messages[-1]
                    if hasattr(last_message, "content"):
                        return last_message.content
                    else:
                        return str(last_message)

            # 전체 딕셔너리를 문자열로 변환
            return str(node_output)
        else:
            # 단순 타입인 경우
            return str(node_output) if node_output else ""

    def get_handled_nodes(self) -> List[str]:
        """처리 가능한 노드 목록 반환"""
        return self.handled_nodes
