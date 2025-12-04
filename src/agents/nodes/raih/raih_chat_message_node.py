"""
RAIH Chat Message Node

채팅 메시지를 데이터베이스에 저장하는 노드
일반 응답 저장 처리
"""

from logging import getLogger
from typing import Any, Callable, Dict, Optional

from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.services import agent_service, chat_channel_service, chat_message_service

logger = getLogger("agents.raih_chat_message_node")


class RAIHChatMessageNode:
    """RAIH 채팅 메시지 저장 노드"""

    def __init__(
        self,
        logger: Any,
        get_agent_id: Callable[[Dict[str, Any]], int],
    ):
        """
        초기화

        Args:
            logger: 로거
            get_agent_id: 에이전트 ID 조회 함수
        """
        self.logger = logger
        self.get_agent_id = get_agent_id

    def _get_agent_code(self, db: Session, agent_id: int) -> str:
        """에이전트 코드 조회"""
        try:
            agent_code = agent_service.get_code_by_id(db, agent_id)
            return agent_code if agent_code else "RAIH"
        except Exception as e:
            self.logger.warning(f"에이전트 코드 조회 실패: {e}")
            return "RAIH"

    async def save_chat_message(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        채팅 메시지를 데이터베이스에 저장합니다.

        Args:
            state: 현재 상태

        Returns:
            저장된 메시지 ID 정보를 포함한 상태 업데이트
        """
        try:
            channel_id = state.get("channel_id")
            user_message_id = state.get("user_message_id")
            agent_id = self.get_agent_id(state)

            if not channel_id:
                self.logger.warning(
                    "[GRAPH] channel_id가 없어 메시지 저장을 건너뜁니다"
                )
                return {}

            # DB 세션 생성
            db: Optional[Session] = None
            try:
                db = next(get_db())
            except Exception as e:
                self.logger.error(f"[GRAPH] DB 세션 생성 실패: {e}")
                return {}

            try:
                agent_code = self._get_agent_code(db, agent_id)

                messages = state.get("messages", [])
                if messages and len(messages) > 0:
                    # 마지막 메시지가 AIMessage인지 확인
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        content = last_message.content
                    elif hasattr(last_message, "content"):
                        content = last_message.content
                    else:
                        content = str(last_message)

                    if content and content.strip():
                        self.logger.info("[GRAPH] 일반 응답을 저장합니다")

                        # 일반 메시지 저장 (lgenie_sync는 별도 노드에서)
                        assistant_message = chat_message_service.create(
                            db,
                            channel_id=channel_id,
                            agent_id=agent_id,
                            message_type=agent_code,
                            content=content.strip(),
                            parent_message_id=user_message_id,
                            message_metadata={
                                "total_token": len(content.split()),
                                "model": ["expert_agent"],
                            },
                        )

                        if assistant_message:
                            chat_channel_service.update_last_message(db, channel_id)
                            self.logger.info(
                                f"[GRAPH] 일반 응답 저장 완료: {assistant_message.id}"
                            )
                            return {
                                "assistant_message_id": assistant_message.id
                            }

                self.logger.warning("[GRAPH] 저장할 메시지가 없습니다")
                return {}

            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"[GRAPH] 채팅 메시지 저장 중 오류: {e}")
            return {}
