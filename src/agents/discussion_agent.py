"""
토론 에이전트 - 실시간 스트리밍 지원
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List

from src.agents.nodes.discussion.discussion_get_materials_node import (
    GetDiscussionMaterialsNode,
)
from src.agents.nodes.discussion.discussion_proceed_node import ProceedDiscussionNode
from src.agents.nodes.discussion.discussion_wrap_up_node import WrapUpDiscussionNode
from src.orchestration.states.caia_state import CAIAAgentState
from src.schemas.sse_response import SSEResponse

logger = logging.getLogger("discussion_agent")


class DiscussionAgent:
    """토론 에이전트"""

    def __init__(self):
        self.logger = logger

        # 토론 노드들 초기화
        self.materials_node = GetDiscussionMaterialsNode(self.logger)
        self.proceed_node = ProceedDiscussionNode(self.logger)
        self.wrap_up_node = WrapUpDiscussionNode(self.logger)

        self.logger.debug("[DISCUSSION_AGENT] 토론 에이전트 초기화 완료")

    async def run_discussion(
        self,
        state: CAIAAgentState,
    ) -> AsyncGenerator[str, None]:
        """
        토론을 실행하고 실시간 스트리밍으로 결과를 반환합니다.

        Args:
            state: CAIAAgentState 객체

        Yields:
            str: SSE 응답 문자열
        """
        self.logger.debug("[DISCUSSION_AGENT] 토론 실행 시작")

        # 토론 상태 초기화 (CAIAAgentState 기반)
        # state에 이미 topic, speakers가 있으면 그것을 사용 (discussion_setting에서 저장된 값)
        discussion_state = {
            **state,
            "topic": state.get("topic") or "",
            "speakers": state.get("speakers") or [],
            "materials": state.get("materials") or [],
            "script": state.get("script") or [],  # 빈 리스트로 초기화 (딕셔너리가 아님)
            "turn_count": 0,
            "summarize": state.get("summarize") or "",
            "total_tokens": state.get("total_tokens")
            or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "discussion_rules": state.get("discussion_rules") or [],  # 토론 규칙 전달
            "tools": state.get("tools"),  # 도구 목록 전달
        }
        self.logger.debug(
            f"[DISCUSSION_AGENT] 토론 상태 초기화 완료 - topic: {discussion_state.get('topic')}, speakers: {len(discussion_state.get('speakers', []))}명, script 초기값: {type(discussion_state.get('script'))}"
        )

        try:
            # 1. 토론 자료 수집 노드 (setup은 이미 discussion_setting에서 완료됨)
            self.logger.debug("[DISCUSSION_AGENT] 1단계: 자료 수집")
            try:
                async for sse_data in self.materials_node.run(discussion_state):
                    yield sse_data
            except asyncio.CancelledError:
                self.logger.warning("[DISCUSSION_AGENT] 자료 수집이 취소됨")
                return
            except Exception as e:
                self.logger.error(f"[DISCUSSION_AGENT] 자료 수집 중 오류: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'자료 수집 중 오류: {str(e)}'})}\n\n"
                return

            # 2. 토론 진행 노드 (취소 방지)
            self.logger.debug("[DISCUSSION_AGENT] 2단계: 토론 진행")
            try:
                async for sse_data in self.proceed_node.run(discussion_state):
                    yield sse_data
            except asyncio.CancelledError:
                self.logger.warning("[DISCUSSION_AGENT] 토론 진행이 취소됨")
                return
            except Exception as e:
                self.logger.error(f"[DISCUSSION_AGENT] 토론 진행 중 오류: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'토론 진행 중 오류: {str(e)}'})}\n\n"
                return

            # 3. 토론 요약 노드 (취소 방지)
            self.logger.debug("[DISCUSSION_AGENT] 3단계: 토론 요약")
            try:
                async for sse_data in self.wrap_up_node.run(discussion_state):
                    yield sse_data
            except asyncio.CancelledError:
                self.logger.warning("[DISCUSSION_AGENT] 토론 요약이 취소됨")
                return
            except Exception as e:
                self.logger.error(f"[DISCUSSION_AGENT] 토론 요약 중 오류: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': f'토론 요약 중 오류: {str(e)}'})}\n\n"
                return

            # 토론 완료 후 스크립트를 원본 상태에 저장
            self.logger.debug(
                f"[DISCUSSION_AGENT] 토론 완료 후 스크립트 확인 - discussion_state에 script 존재: {'script' in discussion_state}, "
                f"script 타입: {type(discussion_state.get('script'))}, "
                f"script 값: {discussion_state.get('script')}"
            )

            if "script" in discussion_state:
                script = discussion_state["script"]
                self.logger.debug(
                    f"[DISCUSSION_AGENT] script 추출 - 타입: {type(script)}, "
                    f"길이: {len(script) if isinstance(script, (list, dict)) else 'N/A'}, "
                    f"값: {script[:2] if isinstance(script, list) and len(script) > 0 else script}"
                )

                if script and isinstance(script, list) and len(script) > 0:
                    state["script"] = script
                    self.logger.info(
                        f"[DISCUSSION_AGENT] 토론 스크립트 저장 완료: {len(script)}개 발언을 state에 저장"
                    )
                    # 스크립트 내용 로깅 (디버깅용)
                    for i, speech in enumerate(script[:3]):  # 처음 3개만 로깅
                        if isinstance(speech, dict) and "speaker" in speech:
                            self.logger.debug(
                                f"[DISCUSSION_AGENT] 발언 {i + 1}: {speech.get('speaker', 'Unknown')}"
                            )
                else:
                    self.logger.warning(
                        f"[DISCUSSION_AGENT] 토론 스크립트가 비어있거나 잘못된 형식입니다: type={type(script)}, "
                        f"len={len(script) if isinstance(script, (list, dict)) else 'N/A'}, value={script}"
                    )
                    # 빈 리스트로 설정하여 나중에 확인 가능하도록
                    state["script"] = []
            else:
                self.logger.warning(
                    "[DISCUSSION_AGENT] discussion_state에 script 키가 없습니다"
                )
                state["script"] = []

            if "summarize" in discussion_state:
                state["summarize"] = discussion_state["summarize"]
                self.logger.debug(
                    f"[DISCUSSION_AGENT] 토론 요약 저장 완료: 요약길이-{len(discussion_state['summarize'])}"
                )

            self.logger.debug("[DISCUSSION_AGENT] 토론 실행 완료")

            # 토론 플로우 전체 토큰 사용량 로깅
            if "total_tokens" in discussion_state:
                tokens = discussion_state["total_tokens"]
                self.logger.info(
                    f"[DISCUSSION_AGENT_TOKEN_USAGE] 토론 플로우 전체 토큰 사용량 - "
                    f"Input: {tokens.get('input_tokens', 0)}, "
                    f"Output: {tokens.get('output_tokens', 0)}, "
                    f"Total: {tokens.get('total_tokens', 0)}"
                )

        except Exception as e:
            self.logger.error(f"[DISCUSSION_AGENT] 토론 실행 중 오류: {e}")
            yield await SSEResponse.create_error(
                f"토론 실행 중 오류가 발생했습니다: {str(e)}"
            ).send()
            raise e

    async def run_for_langgraph(self, state: CAIAAgentState) -> Dict[str, Any]:
        """
        LangGraph 노드에서 사용할 수 있는 토론 실행 메서드
        실시간 스트리밍은 별도로 처리하고, 최종 결과만 반환합니다.
        """
        self.logger.debug("[DISCUSSION_AGENT] LangGraph용 토론 실행")

        # 토론 상태 초기화 (CAIAAgentState 기반)
        # state에 이미 topic, speakers가 있으면 그것을 사용 (discussion_setting에서 저장된 값)
        discussion_state = {
            **state,
            "topic": state.get("topic") or "",
            "speakers": state.get("speakers") or [],
            "materials": state.get("materials") or [],
            "script": state.get("script") or [],  # 빈 리스트로 초기화 (딕셔너리가 아님)
            "turn_count": 0,
            "summarize": state.get("summarize") or "",
            "total_tokens": state.get("total_tokens")
            or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "discussion_rules": state.get("discussion_rules") or [],  # 토론 규칙 전달
            "tools": state.get("tools"),  # 도구 목록 전달
        }

        try:
            materials_result = await self.materials_node.run_for_langgraph(
                discussion_state
            )
            discussion_state["materials"] = materials_result.get("materials", [])

            proceed_result = await self.proceed_node.run_for_langgraph(discussion_state)
            discussion_state["script"] = proceed_result.get("script", [])

            # 3. 토론 요약
            wrap_up_result = await self.wrap_up_node.run_for_langgraph(discussion_state)
            discussion_state["summarize"] = wrap_up_result.get("summarize", "")

            self.logger.debug("[DISCUSSION_AGENT] LangGraph용 토론 실행 완료")

            # LangGraph 상태에 필요한 필드들만 반환
            return {
                "topic": discussion_state.get("topic", ""),
                "speakers": discussion_state.get("speakers", []),
                "materials": discussion_state.get("materials", []),
                "script": discussion_state.get("script", []),
                "summarize": discussion_state.get("summarize", ""),
                "discussion_completed": True,
            }

        except Exception as e:
            self.logger.error(f"[DISCUSSION_AGENT] LangGraph용 토론 실행 중 오류: {e}")
            return {
                "topic": "",
                "speakers": [],
                "materials": [],
                "script": [],
                "summarize": f"토론 실행 중 오류가 발생했습니다: {str(e)}",
                "discussion_completed": False,
                "error": str(e),
            }

    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보를 반환합니다."""
        return {
            "name": "DiscussionAgent",
            "description": "토론 에이전트 - 실시간 스트리밍 지원",
            "capabilities": [
                "토론 주제 설정",
                "전문가 참가자 선정",
                "참고 자료 수집",
                "실시간 토론 진행",
                "토론 요약 및 결론",
            ],
            "supported_intents": ["discussion"],
        }
