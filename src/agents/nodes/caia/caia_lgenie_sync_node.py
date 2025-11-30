"""
CAIA LGenie Sync Node

저장된 채팅 메시지를 LGenie DB에 동기화하는 노드
"""

from logging import getLogger
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models.chat import ChatMessage
from src.database.services.lgenie_sync_service import lgenie_sync_service

logger = getLogger("agents.caia_lgenie_sync_node")


class CAIALGenieSyncNode:
    """CAIA LGenie 동기화 노드"""

    def __init__(
        self,
        logger: Any,
    ):
        """
        초기화

        Args:
            logger: 로거
        """
        self.logger = logger

    async def sync_lgenie(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        저장된 메시지를 LGenie DB에 동기화합니다.

        Args:
            state: 현재 상태

        Returns:
            빈 딕셔너리 (상태 변경 없음)
        """
        try:
            saved_message_ids = state.get("saved_message_ids")
            assistant_message_id = state.get("assistant_message_id")
            channel_id = state.get("channel_id")

            # 동기화할 메시지 ID 목록 생성
            message_ids = []
            if saved_message_ids and isinstance(saved_message_ids, list):
                message_ids = saved_message_ids
            elif assistant_message_id:
                message_ids = [assistant_message_id]

            # DB 세션 생성
            db: Optional[Session] = None
            try:
                db = next(get_db())
            except Exception as e:
                self.logger.error(f"[GRAPH] DB 세션 생성 실패: {e}")
                return {}

            try:
                # discussion 메시지인지 확인
                is_discussion = False
                if channel_id and message_ids:
                    try:
                        # 첫 번째 메시지가 discussion 메시지인지 확인
                        first_message = (
                            db.query(ChatMessage)
                            .filter(ChatMessage.id == message_ids[0])
                            .first()
                        )

                        if first_message:
                            metadata_check = (
                                first_message.message_metadata
                                and isinstance(first_message.message_metadata, dict)
                                and first_message.message_metadata.get(
                                    "is_discussion", False
                                )
                            )
                            type_check = (
                                first_message.message_type
                                and isinstance(first_message.message_type, str)
                                and "_discussion_" in first_message.message_type
                            )
                            is_discussion = metadata_check or type_check
                            
                            self.logger.debug(
                                f"[GRAPH] Discussion 메시지 확인: message_id={message_ids[0]}, "
                                f"message_type={first_message.message_type}, "
                                f"metadata_is_discussion={metadata_check}, "
                                f"type_contains_discussion={type_check}, "
                                f"is_discussion={is_discussion}"
                            )
                        else:
                            self.logger.warning(
                                f"[GRAPH] 첫 번째 메시지를 찾을 수 없습니다: message_id={message_ids[0]}"
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"[GRAPH] Discussion 메시지 확인 중 오류: {e}",
                            exc_info=True
                        )

                # 토론 메시지인 경우 채널 전체 동기화 사용
                if is_discussion and channel_id:
                    self.logger.info(
                        f"[GRAPH] Discussion 메시지 감지: 채널 전체 동기화 시작 (channel_id={channel_id}, "
                        f"message_ids={message_ids})"
                    )
                    
                    # 채널의 모든 메시지를 한 번에 동기화
                    try:
                        success = lgenie_sync_service.sync_channel_with_messages(channel_id)
                        
                        if success:
                            self.logger.info(
                                f"[GRAPH] Discussion 채널 전체 동기화 완료: {channel_id}"
                            )
                        else:
                            self.logger.warning(
                                f"[GRAPH] Discussion 채널 전체 동기화 실패: {channel_id}"
                            )
                    except Exception as e:
                        self.logger.error(
                            f"[GRAPH] Discussion 채널 전체 동기화 중 예외 발생: {channel_id}, error={e}",
                            exc_info=True
                        )
                        success = False
                    
                    # 토론 주제로 제목 업데이트
                    topic = state.get("topic")
                    session_id = state.get("session_id")
                    if topic and session_id:
                        try:
                            update_success = lgenie_sync_service.update_chat_group_title(
                                session_id=session_id,
                                topic=topic,
                            )
                            if update_success:
                                self.logger.info(
                                    f"[GRAPH] 토론 제목 업데이트 완료: {session_id} -> 토론: {topic}"
                                )
                            else:
                                self.logger.warning(
                                    f"[GRAPH] 토론 제목 업데이트 실패: {session_id}"
                                )
                        except Exception as e:
                            self.logger.error(
                                f"[GRAPH] 토론 제목 업데이트 중 오류: {e}"
                            )
                    
                    return {}
                
                # 일반 메시지인 경우 기존 로직 사용
                if not message_ids:
                    self.logger.warning("[GRAPH] 동기화할 메시지 ID가 없습니다")
                    return {}

                synced_count = 0
                failed_count = 0

                for message_id in message_ids:
                    try:
                        # 메시지 조회
                        message = (
                            db.query(ChatMessage)
                            .filter(ChatMessage.id == message_id)
                            .first()
                        )

                        if not message:
                            self.logger.warning(
                                f"[GRAPH] 메시지를 찾을 수 없습니다: {message_id}"
                            )
                            failed_count += 1
                            continue

                        # LGenie 동기화
                        success = lgenie_sync_service.sync_chat_message(message, db)

                        if success:
                            synced_count += 1
                            self.logger.debug(
                                f"[GRAPH] 메시지 동기화 완료: {message_id}"
                            )
                        else:
                            failed_count += 1
                            self.logger.warning(
                                f"[GRAPH] 메시지 동기화 실패: {message_id}"
                            )

                    except Exception as e:
                        failed_count += 1
                        self.logger.error(
                            f"[GRAPH] 메시지 동기화 중 오류 (message_id={message_id}): {e}"
                        )

                if synced_count > 0:
                    self.logger.info(
                        f"[GRAPH] LGenie 동기화 완료: {synced_count}개 성공, {failed_count}개 실패"
                    )
                elif failed_count > 0:
                    self.logger.warning(
                        f"[GRAPH] LGenie 동기화 실패: {failed_count}개 모두 실패"
                    )

            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

            return {}

        except Exception as e:
            self.logger.error(f"[GRAPH] LGenie 동기화 중 오류: {e}")
            return {}
