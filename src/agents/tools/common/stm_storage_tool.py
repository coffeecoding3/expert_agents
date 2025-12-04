"""
STM Storage Tool
단기 메모리(STM) 저장 도구 - 대화 메시지를 STM에 저장
공통 tool로 모든 에이전트에서 사용됩니다.
"""

from logging import getLogger
from typing import Any, Dict, List

from src.agents.tools.base_tool import BaseTool
from langchain_core.messages import AIMessage, HumanMessage

logger = getLogger("agents.tools.stm_storage")


class STMStorageTool(BaseTool):
    """STM 메시지 저장 도구 - 데이터베이스 인터페이스"""

    name = "stm_storage"
    description = "대화 메시지를 단기 메모리(STM)에 저장합니다."

    def __init__(self, memory_manager: Any):
        """초기화"""
        self.memory_manager = memory_manager

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """STM 메시지 저장 실행"""
        # 입력 검증
        if not isinstance(tool_input, dict):
            return {"error": "tool_input must be a dictionary", "success": False}

        try:
            user_id = tool_input.get("user_id")
            agent_id = tool_input.get("agent_id", 1)
            session_id = tool_input.get("session_id")
            messages = tool_input.get("messages", [])
            discussion_script = tool_input.get("discussion_script") or tool_input.get(
                "script"
            )
            summarize = tool_input.get("summarize", "")
            user_query = tool_input.get("user_query", "")

            if not user_id:
                return {"error": "user_id is required", "success": False}

            logger.info("[STM_STORAGE] 대화 메시지를 저장합니다")
            logger.debug(
                f"[STM_STORAGE] 입력 데이터 확인 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}, "
                f"messages={len(messages) if messages else 0}, "
                f"discussion_script={len(discussion_script) if discussion_script else 0}, "
                f"discussion_script_type={type(discussion_script)}, "
                f"summarize={len(summarize) if summarize else 0}, user_query={user_query[:50] if user_query else ''}"
            )

            # 토론 스크립트가 있으면 우선 처리
            if (
                discussion_script
                and isinstance(discussion_script, list)
                and len(discussion_script) > 0
            ):
                logger.info(
                    f"[STM_STORAGE] 토론 스크립트를 저장합니다: {len(discussion_script)}개 발언"
                )
                content = self._format_discussion_content(
                    discussion_script=discussion_script,
                    summarize=summarize,
                    user_query=user_query,
                )
                logger.debug(
                    f"[STM_STORAGE] 토론 스크립트 포맷팅 완료 - user 길이={len(content.get('user', ''))}, bot 길이={len(content.get('bot', ''))}"
                )
            elif messages and len(messages) >= 1:
                # 일반 대화 메시지 저장
                logger.info("[STM_STORAGE] 일반 대화 메시지를 저장합니다")
                content = self._format_regular_content(messages)
            else:
                logger.warning(
                    f"[STM_STORAGE] 저장할 메시지가 없습니다: messages={len(messages) if messages else 0}, "
                    f"discussion_script={len(discussion_script) if discussion_script else 0}, "
                    f"discussion_script_type={type(discussion_script)}"
                )
                return {"success": False, "error": "insufficient_messages"}

            logger.debug(
                f"[STM_STORAGE] memory_manager.save_stm_message 호출 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}"
            )
            success = self.memory_manager.save_stm_message(
                user_id=user_id,
                content=content,
                agent_id=agent_id,
                session_id=session_id,
            )

            if success:
                logger.info(f"[STM_STORAGE] 대화 메시지 저장이 완료되었습니다 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}")
            else:
                logger.error(f"[STM_STORAGE] 대화 메시지 저장 실패 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}")
            
            return {"success": success, "saved": True}

        except Exception as e:
            logger.error(f"[STM_STORAGE] 대화 메시지 저장 중 오류: {e}")
            return {"error": str(e), "success": False}

    def _format_discussion_content(
        self,
        discussion_script: List[Dict[str, Any]],
        summarize: str = "",
        user_query: str = "",
    ) -> Dict[str, str]:
        """
        토론 스크립트를 STM 저장용 포맷으로 변환

        Args:
            discussion_script: 토론 스크립트 리스트 (각 항목은 {"speaker": str, "speech": str} 형식)
            summarize: 토론 요약 (Wow Point)
            user_query: 사용자 질의

        Returns:
            {"user": str, "bot": str} 형식의 content 딕셔너리
        """
        bot_content_parts = []

        # 각 발언을 포맷팅
        for speech_item in discussion_script:
            if (
                isinstance(speech_item, dict)
                and "speaker" in speech_item
                and "speech" in speech_item
            ):
                speaker = speech_item.get("speaker", "Unknown")
                speech = speech_item.get("speech", "").strip()
                if speech:
                    bot_content_parts.append(f"{speaker}: {speech}")

        # 요약이 있으면 추가 (문자열인 경우만)
        if summarize:
            # summarize가 문자열인지 확인
            if isinstance(summarize, str) and summarize.strip():
                bot_content_parts.append(f"\n🌟 **Insight**\n{summarize.strip()}")
            elif isinstance(summarize, (list, dict)):
                # summarize가 리스트나 딕셔너리인 경우 (예: 토론 요약 결과)
                # 문자열로 변환 시도
                try:
                    if isinstance(summarize, list) and len(summarize) > 0:
                        # 리스트의 첫 번째 항목이 AIMessage인 경우 content 추출
                        first_item = summarize[0]
                        if hasattr(first_item, 'content'):
                            summarize_str = first_item.content
                        else:
                            summarize_str = str(first_item)
                    elif isinstance(summarize, dict):
                        # 딕셔너리에서 content나 message 추출
                        summarize_str = summarize.get('content') or summarize.get('message') or str(summarize)
                    else:
                        summarize_str = str(summarize)
                    
                    if summarize_str and isinstance(summarize_str, str) and summarize_str.strip():
                        bot_content_parts.append(f"\n🌟 **Insight**\n{summarize_str.strip()}")
                except Exception as e:
                    logger.warning(f"[STM_STORAGE] summarize 변환 실패: {e}, type={type(summarize)}")

        bot_content = "\n".join(bot_content_parts)

        return {"user": user_query or "", "bot": bot_content}

    def _format_regular_content(self, messages):
        """일반 대화 메시지를 STM 저장용 포맷으로 변환"""
        if len(messages) >= 2:
            # 마지막 사용자 메시지와 AI 응답을 저장
            user_msg = (
                messages[0] if isinstance(messages[0], HumanMessage) else messages[1]
            )
            ai_msg = messages[1] if isinstance(messages[1], AIMessage) else messages[0]

            if user_msg and ai_msg:
                # 메시지 포맷 구성
                content = {"user": user_msg.content, "bot": ai_msg.content}
            else:
                # 메시지가 없으면 빈 문자열로 처리
                content = {"user": "", "bot": ""}
        else:
            # 메시지가 1개만 있는 경우
            single_msg = messages[-1]
            if single_msg:
                # 단일 메시지를 user와 bot으로 분리하거나 bot만 저장
                content = {"user": "", "bot": single_msg.content}
            else:
                content = {"user": "", "bot": ""}

        return content

    def _get_input_schema(self) -> Dict[str, Any]:
        """입력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "사용자 ID"},
                "agent_id": {
                    "type": "integer",
                    "description": "에이전트 ID (기본값: 1)",
                },
                "session_id": {"type": "string", "description": "세션 ID"},
                "messages": {"type": "array", "description": "저장할 메시지 목록"},
                "discussion_script": {
                    "type": "array",
                    "description": "토론 스크립트 (선택사항)",
                },
                "script": {
                    "type": "array",
                    "description": "토론 스크립트 별칭 (선택사항)",
                },
                "summarize": {"type": "string", "description": "토론 요약 (선택사항)"},
                "user_query": {
                    "type": "string",
                    "description": "사용자 질의 (선택사항)",
                },
            },
            "required": ["user_id"],
        }

    def _get_output_schema(self) -> Dict[str, Any]:
        """출력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "저장 성공 여부"},
                "saved": {"type": "boolean", "description": "실제 저장 여부"},
                "error": {"type": "string", "description": "오류 메시지 (실패시)"},
            },
        }
