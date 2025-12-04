from typing import Any, Callable, Dict

from src.agents.tools.caia.memory_candidate_extractor_tool import (
    MemoryCandidateExtractorTool,
)


class RAIHMemoryNode:
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
            session_context = stm_msgs

            # 8. MemoryCandidateExtractorTool 직접 호출 (사용자 쿼리만 사용)
            tool_input = {
                "user_id": user_id,
                "agent_id": agent_id,
                "session_content": session_context,  # 이전 대화 컨텍스트 (사용자 메시지만)
                "user_query": user_query,  # 사용자 질의 (메모리 추출 대상)
                "importance": float(importance),
            }
            self.logger.info("[GRAPH][post] 메모리 후보 추출 도구를 실행합니다")

            memory_tool = MemoryCandidateExtractorTool()
            payload = await memory_tool.run(tool_input)
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
