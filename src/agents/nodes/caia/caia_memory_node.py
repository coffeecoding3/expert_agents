from typing import Any, Callable, Dict

from src.agents.tools.caia.memory_candidate_extractor_tool import (
    MemoryCandidateExtractorTool,
)


class CAIAMemoryNode:
    def __init__(
        self,
        memory_manager: Any,
        logger: Any,
        get_agent_id: Callable[[Dict[str, Any]], int],
    ):
        self.memory_manager = memory_manager
        self.logger = logger
        self.get_agent_id = get_agent_id

    async def retrieve_memory(self, state: Dict[str, Any]) -> Dict[str, Any]:
        user_id = state.get("user_id")
        agent_id = self.get_agent_id(state)
        session_id = state.get("session_id")
        self.logger.info("[GRAPH][1/7] 메모리를 검색합니다")
        memory = self.memory_manager.get_stm_recent_messages(
            user_id, agent_id, k=5, session_id=session_id
        )
        self.logger.info(f"[GRAPH][1/7] 메모리 검색 완료: {len(memory)}개")
        return {"memory": memory}

    async def extract_and_save_memory_new(
        self, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """세션 전체 대화에서 메모리 후보를 추출해 저장 (툴 호출).
        Returns: { ok: bool, saved_count: int, saved: list, error?: str, raw?: Any }
        """

        self.logger.info("[GRAPH][post] 메모리 후보를 추출합니다")

        user_id = state.get("user_id")
        agent_id = self.get_agent_id(state)

        ## 대화이력, query 준비
        user_query = state.get("user_query")
        user_context = state.get("user_context")
        chat_history = user_context.get("recent_messages", [])
        existing_memory = user_context.get("long_term_memories", "")

        self.logger.info("[GRAPH][post] 메모리 후보 추출 도구를 실행합니다")

        try:
            memory_tool = MemoryCandidateExtractorTool()
            payload = await memory_tool.run_new(
                user_id=user_id,
                agent_id=agent_id,
                user_query=user_query,
                chat_history=chat_history,
                existing_memory=existing_memory,
            )
            self.logger.info(f"[GRAPH][post] LTM 처리 완료: {payload}")
            return {"ok": True}

        except Exception as e:
            self.logger.error(f"[GRAPH][post] LTM 처리 중 오류: {e}")
            return {"ok": False, "error": str(e)}

    async def extract_and_save_memory(
        self, state: Dict[str, Any], importance: float = 0.7
    ) -> Dict[str, Any]:
        """세션 전체 대화에서 메모리 후보를 추출해 저장 (툴 호출).
        Returns: { ok: bool, saved_count: int, saved: list, error?: str, raw?: Any }
        """
        try:
            self.logger.info("[GRAPH][post] 메모리 후보를 추출합니다")
            user_id = state.get("user_id")
            agent_id = self.get_agent_id(state)
            session_id = state.get("session_id")

            # 1. STM에서 메시지 조회 시도
            stm_msgs = (
                self.memory_manager.get_all_session_messages(
                    user_id, agent_id, session_id=session_id
                )
                or []
            )
            self.logger.debug(
                "[GRAPH][post] STM에서 조회한 메시지 수: %d", len(stm_msgs)
            )

            # 2. STM에 메시지가 없으면 현재 세션의 messages 파라미터 사용
            # current_messages = state.get("messages", [])
            # self.logger.debug(
            #     "[GRAPH][post] 현재 세션 메시지 수: %d", len(current_messages)
            # )

            # 3. 메시지 소스 결정 (STM 우선, 없으면 현재 세션 메시지)
            # msgs = stm_msgs if stm_msgs else current_messages
            msgs = stm_msgs

            if not isinstance(msgs, list) or not msgs:
                self.logger.info("[GRAPH][post] 메시지가 없어 메모리 추출을 건너뜁니다")
                return {
                    "ok": False,
                    "saved_count": 0,
                    "saved": [],
                    "error": "no_messages",
                }

            # 4. 사용자의 최신 질의 추출 (메모리 추출 대상)

            user_query = state.get("user_query")
            # user_query = ""
            # self.logger.debug(
            #     f"[GRAPH][post] 메시지 분석 시작 - 총 {len(msgs)}개 메시지"
            # )

            # if msgs and len(msgs) >= 1:
            #     # STM 메시지인 경우와 현재 세션 메시지인 경우를 구분하여 처리
            #     if stm_msgs:
            #         self.logger.debug(
            #             "[GRAPH][post] STM 메시지에서 사용자 쿼리 추출 시도"
            #         )
            #         # STM 메시지: 마지막 메시지가 사용자 메시지
            #         user_msg = msgs[-1] if len(msgs) >= 1 else None
            #         if user_msg:
            #             user_query = str(user_msg.get("content") or "").strip()
            #             self.logger.debug(
            #                 f"[GRAPH][post] STM에서 추출한 사용자 쿼리: '{user_query[:50]}...'"
            #             )
            #     else:
            #         self.logger.debug(
            #             "[GRAPH][post] 현재 세션 메시지에서 사용자 쿼리 추출 시도"
            #         )
            #         # 현재 세션 메시지: 토론 에이전트의 경우 메시지가 1개일 수 있음 (사용자 메시지만)
            #         if len(msgs) >= 2:
            #             # 일반적인 경우: 마지막에서 두 번째가 사용자 메시지 (마지막은 AI 응답)
            #             user_msg = msgs[-2]
            #         elif len(msgs) == 1:
            #             # 토론 에이전트의 경우: 메시지가 1개면 사용자 메시지일 가능성이 높음
            #             user_msg = msgs[0]
            #             self.logger.debug(
            #                 "[GRAPH][post] 메시지가 1개 - 사용자 메시지로 추정"
            #             )
            #         else:
            #             user_msg = None

            #         if user_msg:
            #             # ChatMessage 객체인 경우 content 속성 사용
            #             if hasattr(user_msg, "content"):
            #                 user_query = str(user_msg.content or "").strip()
            #                 self.logger.debug(
            #                     f"[GRAPH][post] ChatMessage에서 추출한 사용자 쿼리: '{user_query[:50]}...'"
            #                 )
            #             else:
            #                 user_query = str(user_msg.get("content") or "").strip()
            #                 self.logger.debug(
            #                     f"[GRAPH][post] 딕셔너리에서 추출한 사용자 쿼리: '{user_query[:50]}...'"
            #                 )
            #         else:
            #             self.logger.debug(
            #                 "[GRAPH][post] 사용자 메시지를 찾을 수 없음 (메시지 수 부족)"
            #             )

            #     # 메시지 구조 디버깅
            #     for i, msg in enumerate(msgs):
            #         if hasattr(msg, "content"):
            #             self.logger.debug(
            #                 f"[GRAPH][post] 메시지 {i}: ChatMessage - '{str(msg.content)[:30]}...'"
            #             )
            #         else:
            #             self.logger.debug(
            #                 f"[GRAPH][post] 메시지 {i}: 딕셔너리 - '{str(msg.get('content', ''))[:30]}...'"
            #             )
            # else:
            #     self.logger.debug("[GRAPH][post] 메시지가 없어 사용자 쿼리 추출 불가")

            # # 5. 사용자 쿼리 또는 토론 요약이 없으면 메모리 추출하지 않음
            # discussion_summary = state.get("summarize", "")
            # if not user_query and not discussion_summary:
            #     self.logger.info(
            #         "[GRAPH][post] 사용자 쿼리와 토론 요약이 모두 없어 메모리 추출을 건너뜁니다"
            #     )
            #     return {
            #         "ok": False,
            #         "saved_count": 0,
            #         "saved": [],
            #         "error": "no_user_query_or_summary",
            #     }

            # # 사용자 쿼리가 없지만 토론 요약이 있는 경우, 토론 요약을 사용자 쿼리로 사용
            # if not user_query and discussion_summary:
            #     user_query = f"토론 주제: {discussion_summary.strip()}"
            #     self.logger.info(
            #         "[GRAPH][post] 사용자 쿼리가 없어 토론 요약을 사용자 쿼리로 사용합니다"
            #     )

            # 6. 이전 대화 컨텍스트 생성 (사용자 메시지만 포함)
            # context_lines: list[str] = []
            # for m in msgs[:-1]:  # 마지막 AI 응답 제외
            #     try:
            #         if stm_msgs:
            #             # STM 메시지: content 속성 사용
            #             content = str(m.get("content") or "").strip()
            #         else:
            #             # 현재 세션 메시지: ChatMessage 객체 처리
            #             if hasattr(m, "content"):
            #                 content = str(m.content or "").strip()
            #             else:
            #                 content = str(m.get("content") or "").strip()

            #         if content:
            #             context_lines.append(content)
            #     except Exception:
            #         continue

            # 7. 토론 요약 정보 추가 (토론 에이전트의 경우) ⚠️ 토론시 대화이력 처리?
            # if discussion_summary and discussion_summary.strip():
            #     context_lines.append(f"토론 요약: {discussion_summary.strip()}")
            #     self.logger.debug("[GRAPH][post] 토론 요약을 컨텍스트에 추가했습니다")

            session_context = stm_msgs

            # 8. MemoryCandidateExtractorTool 직접 호출 (사용자 쿼리만 사용)
            tool_input = {
                "user_id": user_id,
                "agent_id": agent_id,
                "session_content": session_context,  # 이전 대화 컨텍스트 (사용자 메시지만)
                "user_query": user_query,  # 사용자 질의 (메모리 추출 대상)
                "importance": float(importance),
            }
            self.logger.info(f"[GRAPH][post] 메모리 후보 추출 도구를 실행합니다 - tool_input: {tool_input}")

            memory_tool = MemoryCandidateExtractorTool()
            self.logger.info(f"[GRAPH][post] MemoryCandidateExtractorTool 인스턴스 생성 완료")
            payload = await memory_tool.run(tool_input)
            self.logger.info(f"[GRAPH][post] MemoryCandidateExtractorTool.run 호출 완료 - payload: {payload}")
            ok = False
            saved = []
            if isinstance(payload, dict):
                ok = bool(payload.get("ok"))
                saved = payload.get("saved") or []
            self.logger.info(
                f"[GRAPH][post] 메모리 후보 추출 완료: {len(saved) if isinstance(saved, list) else 0}개 저장"
            )
            return {
                "ok": ok,
                "saved_count": (len(saved) if isinstance(saved, list) else 0),
                "saved": (saved if isinstance(saved, list) else []),
                "raw": payload,
            }
        except Exception as e:
            self.logger.error(f"[GRAPH][post] 메모리 후보 추출 중 오류: {e}")
            return {"ok": False, "saved_count": 0, "saved": [], "error": str(e)}
