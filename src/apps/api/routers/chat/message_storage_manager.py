"""
Message Storage Manager
메시지 저장 및 관리 담당
"""

from logging import getLogger
from typing import Optional

from sqlalchemy.orm import Session

from src.database.services import chat_channel_service, chat_message_service

logger = getLogger("message_storage_manager")


class MessageStorageManager:
    """메시지 저장 매니저 - 메시지 저장 및 관리"""

    def __init__(self):
        self.logger = logger

    async def save_general_response(
        self,
        db: Session,
        channel_id: int,
        agent_id: int,
        agent_name: str,
        user_message_id: int,
        content: str,
    ) -> Optional[int]:
        """일반 응답을 데이터베이스에 저장합니다."""
        if not (db and channel_id and content.strip()):
            return None

        try:
            assistant_message = chat_message_service.create_message(
                db,
                channel_id=channel_id,
                agent_id=agent_id,
                message_type=agent_name,
                content=content.strip(),
                parent_message_id=user_message_id,
                message_metadata={
                    "total_token": len(content.split()),
                    "model": ["expert_agent"],
                },
            )

            if assistant_message:
                chat_channel_service.update_last_message(db, channel_id)
                self.logger.debug(
                    f"[MESSAGE_STORAGE] 일반 응답 저장 완료: {assistant_message.id}"
                )
                return assistant_message.id

        except Exception as e:
            self.logger.error(f"[MESSAGE_STORAGE] 일반 응답 저장 실패: {e}")
            return None
