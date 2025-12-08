"""
채팅 관련 데이터베이스 서비스

ChatChannel, ChatMessage 관련 서비스들
"""

from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import asc, desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import ChatChannel, ChatChannelStatus, ChatMessage, MessageType
from .base_orm_service import ORMService
from .lgenie_sync_service import lgenie_sync_service

logger = getLogger("database")


class ChatChannelService(ORMService[ChatChannel]):
    """채팅방 서비스"""

    def __init__(self):
        super().__init__(ChatChannel)

    def get_by_session_id(self, db: Session, session_id: str) -> Optional[ChatChannel]:
        """세션 ID로 채팅방 조회"""
        try:
            return (
                db.query(ChatChannel)
                .filter(ChatChannel.session_id == session_id)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"세션 ID로 채팅방 조회 실패: {e}")
            return None

    def get_by_session_id_from_lgenie(self, session_id: str) -> bool:
        """LGenie DB에서 세션 ID로 채팅방 조회"""
        try:
            exists = lgenie_sync_service.check_chat_group_exists(session_id)
            if exists:
                return True
        except Exception as e:
            logger.error(f"LGenie DB에서 세션 ID로 채팅방 조회 실패: {e}")
            return False

    def get_user_channels(
        self,
        db: Session,
        user_id: int,
        agent_id: Optional[int] = None,
        status: Optional[ChatChannelStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ChatChannel], int]:
        """사용자의 채팅방 목록 조회 (페이지네이션 지원)"""
        try:
            query = db.query(ChatChannel).filter(ChatChannel.user_id == user_id)

            if agent_id:
                query = query.filter(ChatChannel.agent_id == agent_id)

            if status:
                query = query.filter(ChatChannel.status == status)

            # 전체 개수 조회
            total_count = query.count()

            # 페이지네이션 적용
            offset = (page - 1) * page_size
            channels = (
                query.order_by(desc(ChatChannel.last_message_at))
                .offset(offset)
                .limit(page_size)
                .all()
            )

            return channels, total_count
        except SQLAlchemyError as e:
            logger.error(f"사용자 채팅방 조회 실패: {e}")
            return [], 0

    def get_agent_channels(
        self,
        db: Session,
        agent_id: int,
        status: Optional[ChatChannelStatus] = None,
        limit: int = 50,
    ) -> List[ChatChannel]:
        """에이전트의 채팅방 목록 조회"""
        try:
            query = db.query(ChatChannel).filter(ChatChannel.agent_id == agent_id)

            if status:
                query = query.filter(ChatChannel.status == status)

            return query.order_by(desc(ChatChannel.last_message_at)).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"에이전트 채팅방 조회 실패: {e}")
            return []

    def update_last_message(
        self, db: Session, channel_id: int, message_count: int = None
    ) -> bool:
        """마지막 메시지 시간 및 메시지 수 업데이트"""
        try:
            channel = db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
            if channel:
                channel.last_message_at = func.current_timestamp()
                if message_count is not None:
                    channel.message_count = message_count
                db.commit()
                return True
            return False
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"채팅방 마지막 메시지 업데이트 실패: {e}")
            return False

    def archive_channel(self, db: Session, channel_id: int) -> bool:
        """채팅방 아카이브"""
        try:
            channel = db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
            if channel:
                channel.status = ChatChannelStatus.ARCHIVED
                db.commit()
                return True
            return False
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"채팅방 아카이브 실패: {e}")
            return False

    def create_channel(self, db: Session, **kwargs) -> Optional[ChatChannel]:
        """채팅방 생성 (LGenie 동기화 포함)"""
        try:
            # Main DB에 채널 생성
            channel = self.create(db, **kwargs)
            if not channel:
                return None

            # LGenie DB에 동기화 (실패해도 Main DB 작업은 성공으로 처리)
            try:
                lgenie_sync_service.sync_chat_channel(channel.id)
            except Exception as e:
                logger.warning(f"LGenie 채널 동기화 실패 (무시됨): {e}")

            return channel
        except Exception as e:
            logger.error(f"채팅방 생성 실패: {e}")
            return None


class ChatMessageService(ORMService[ChatMessage]):
    """채팅 메시지 서비스"""

    def __init__(self):
        super().__init__(ChatMessage)

    def get_channel_messages(
        self,
        db: Session,
        channel_id: int,
        message_type: Optional[MessageType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ChatMessage]:
        """채팅방의 메시지 목록 조회"""
        try:
            query = db.query(ChatMessage).filter(
                ChatMessage.channel_id == channel_id, ChatMessage.is_deleted == False
            )

            if message_type:
                query = query.filter(ChatMessage.message_type == message_type)

            # 모든 메시지를 가져온 후 discussion_order로 정렬
            messages = query.all()

            # discussion_order로 정렬: -1(user) < 0(setup) < 1~N(script) < N+1(wrapup)
            # discussion_order가 없으면 큰 값으로 설정하여 뒤로 밀림
            def get_sort_key(msg: ChatMessage) -> tuple:
                """정렬 키 생성: (discussion_order가 있으면 그것, 없으면 큰 값), created_at"""
                metadata = msg.message_metadata
                if metadata and isinstance(metadata, dict):
                    discussion_order = metadata.get("discussion_order")
                    if discussion_order is not None and isinstance(
                        discussion_order, int
                    ):
                        return (discussion_order, msg.created_at or datetime.min)
                # discussion_order가 없으면 큰 값으로 설정하여 뒤로 밀림
                return (999999, msg.created_at or datetime.min)

            sorted_messages = sorted(messages, key=get_sort_key)

            # 페이지네이션 적용
            return sorted_messages[offset : offset + limit]
        except SQLAlchemyError as e:
            logger.error(f"채팅방 메시지 조회 실패: {e}")
            return []

    def get_recent_messages(
        self, db: Session, channel_id: int, limit: int = 20
    ) -> List[ChatMessage]:
        """최근 메시지 조회"""
        try:
            return (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.is_deleted == False,
                )
                .order_by(desc(ChatMessage.created_at))
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"최근 메시지 조회 실패: {e}")
            return []

    def get_message_thread(
        self, db: Session, parent_message_id: int
    ) -> List[ChatMessage]:
        """메시지 스레드 조회 (답변 관계)"""
        try:
            messages = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.parent_message_id == parent_message_id,
                    ChatMessage.is_deleted == False,
                )
                .all()
            )

            # discussion_order로 정렬: -1(user) < 0(setup) < 1~N(script) < N+1(wrapup)
            # discussion_order가 없으면 큰 값으로 설정하여 뒤로 밀림
            def get_sort_key(msg: ChatMessage) -> tuple:
                """정렬 키 생성: (discussion_order가 있으면 그것, 없으면 큰 값), created_at"""
                metadata = msg.message_metadata
                if metadata and isinstance(metadata, dict):
                    discussion_order = metadata.get("discussion_order")
                    if discussion_order is not None and isinstance(
                        discussion_order, int
                    ):
                        return (discussion_order, msg.created_at or datetime.min)
                # discussion_order가 없으면 큰 값으로 설정하여 뒤로 밀림
                return (999999, msg.created_at or datetime.min)

            return sorted(messages, key=get_sort_key)
        except SQLAlchemyError as e:
            logger.error(f"메시지 스레드 조회 실패: {e}")
            return []

    def soft_delete_message(self, db: Session, message_id: int) -> bool:
        """메시지 소프트 삭제"""
        try:
            message = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
            if message:
                message.is_deleted = True
                db.commit()
                return True
            return False
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"메시지 소프트 삭제 실패: {e}")
            return False

    def get_message_stats(self, db: Session, channel_id: int) -> Dict[str, int]:
        """채팅방 메시지 통계"""
        try:
            total = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.is_deleted == False,
                )
                .count()
            )

            user_messages = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.message_type == MessageType.USER,
                    ChatMessage.is_deleted == False,
                )
                .count()
            )

            assistant_messages = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.message_type != MessageType.USER,
                    ChatMessage.is_deleted == False,
                )
                .count()
            )

            return {
                "total": total,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
            }
        except SQLAlchemyError as e:
            logger.error(f"메시지 통계 조회 실패: {e}")
            return {"total": 0, "user_messages": 0, "assistant_messages": 0}

    def create_message(self, db: Session, **kwargs) -> Optional[ChatMessage]:
        """채팅 메시지 생성 (LGenie 동기화 포함)"""
        try:
            # Main DB에 메시지 생성
            message = self.create(db, **kwargs)
            if not message:
                return None

            # LGenie DB에 동기화 (실패해도 Main DB 작업은 성공으로 처리)
            try:
                lgenie_sync_service.sync_chat_message(message, db)
            except Exception as e:
                logger.warning(f"LGenie 메시지 동기화 실패 (무시됨): {e}")

            return message
        except Exception as e:
            logger.error(f"채팅 메시지 생성 실패: {e}")
            return None

    def save_discussion_script(
        self,
        db: Session,
        channel_id: int,
        agent_id: int,
        user_message_id: Optional[int],
        script: List[Dict[str, Any]],
        agent_code: str,
    ) -> Dict[str, Any]:
        """
        토론 스크립트 전체를 저장합니다.

        Args:
            db: DB 세션
            channel_id: 채널 ID
            agent_id: 에이전트 ID
            user_message_id: 사용자 메시지 ID
            script: 토론 스크립트 리스트 (각 항목은 {"speaker": str, "speech": str} 형식)
            agent_code: 에이전트 코드

        Returns:
            저장된 메시지 ID 정보를 포함한 딕셔너리
            - assistant_message_id: 마지막 저장된 메시지 ID
            - saved_message_ids: 저장된 모든 메시지 ID 리스트
        """
        if not script or not isinstance(script, list) or len(script) == 0:
            logger.warning("[CHAT_SERVICE] 저장할 토론 스크립트가 없습니다")
            return {}

        saved_message_ids = []
        logger.info(f"[CHAT_SERVICE] 토론 스크립트를 저장합니다: {len(script)}개 발언")

        # 기준 시간 설정: user_message 또는 setup 메시지의 created_at 사용
        # 우선순위: setup 메시지 > user_message > 현재 시간
        base_time = None
        try:
            from src.database.models.chat import ChatMessage

            # 1. setup 메시지의 created_at 조회 (discussion_order = 0)
            setup_message = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.message_metadata.isnot(None),
                )
                .all()
            )
            for msg in setup_message:
                if (
                    msg.message_metadata
                    and isinstance(msg.message_metadata, dict)
                    and msg.message_metadata.get("discussion_order") == 0
                ):
                    base_time = msg.created_at
                    logger.info(
                        f"[CHAT_SERVICE] Setup 메시지의 created_at을 기준으로 사용: {base_time}"
                    )
                    break
            
            # 2. setup 메시지가 없으면 user_message의 created_at 조회
            if base_time is None and user_message_id:
                user_message = db.query(ChatMessage).filter(
                    ChatMessage.id == user_message_id
                ).first()
                if user_message and user_message.created_at:
                    base_time = user_message.created_at
                    logger.info(
                        f"[CHAT_SERVICE] User message의 created_at을 기준으로 사용: {base_time}"
                    )
            
            # 3. 둘 다 없으면 현재 시간 사용
            if base_time is None:
                from datetime import datetime
                base_time = datetime.now()
                logger.warning(
                    "[CHAT_SERVICE] setup 메시지와 user_message를 찾을 수 없어 현재 시간을 기준으로 사용"
                )
            else:
                # setup이 있으면 setup + 1초부터, user_message만 있으면 user_message + 2초부터 시작
                # (setup이 1초, script는 2초부터)
                from datetime import timedelta
                if any(
                    msg.message_metadata
                    and isinstance(msg.message_metadata, dict)
                    and msg.message_metadata.get("discussion_order") == 0
                    for msg in setup_message
                ):
                    # setup이 있으면 setup + 1초부터 시작 (setup이 이미 user_message + 1초이므로)
                    base_time = base_time + timedelta(seconds=1)
                else:
                    # user_message만 있으면 user_message + 2초부터 시작
                    base_time = base_time + timedelta(seconds=2)
        except Exception as e:
            logger.warning(f"[CHAT_SERVICE] 기준 시간 조회 실패: {e}")
            from datetime import datetime
            base_time = datetime.now()

        for i, speech in enumerate(script):
            if isinstance(speech, dict) and "speaker" in speech and "speech" in speech:
                speaker_name = speech["speaker"]
                speech_content = speech["speech"]

                if not speech_content or not speech_content.strip():
                    logger.warning(
                        f"[CHAT_SERVICE] 빈 발언 내용 건너뜀: {speaker_name} (순서: {i + 1})"
                    )
                    continue

                # message_type을 {agent_code}_discussion_{speaker_name} 형식으로 설정
                message_type = f"{agent_code}_discussion_{speaker_name}"

                # created_at을 명시적으로 설정하여 순서 보장
                # base_time이 이미 setup 또는 user_message 기준으로 계산되었으므로
                # i번째 발언은 base_time + i초로 설정 (첫 번째 발언이 base_time)
                from datetime import timedelta

                message_time = base_time + timedelta(seconds=i)

                # 각 발언을 별도 메시지로 저장
                # discussion_order는 speaker_order와 동일하게 설정 (1부터 시작)
                # setup이 0번이므로 speaker들은 1부터 시작
                speaker_message = self.create_message(
                    db,
                    channel_id=channel_id,
                    agent_id=agent_id,
                    message_type=message_type,
                    content=f"{speaker_name}: {speech_content.strip()}",
                    parent_message_id=user_message_id,
                    created_at=message_time,  # 명시적으로 시간 설정
                    message_metadata={
                        "total_token": len(speech_content.split()),
                        "model": ["expert_agent"],
                        "speaker_order": i + 1,
                        "discussion_order": i + 1,  # setup(0) 다음부터 시작
                        "speaker_name": speaker_name,
                        "is_host": "진행자" in speaker_name
                        or "host" in speaker_name.lower(),
                        "is_discussion": True,
                        "stage": "proceed",
                    },
                )

                if speaker_message:
                    saved_message_ids.append(speaker_message.id)
                    logger.info(
                        f"[CHAT_SERVICE] 토론 발언 저장 완료: {speaker_name} (순서: {i + 1}) - 메시지 ID: {speaker_message.id}"
                    )
                else:
                    logger.error(
                        f"[CHAT_SERVICE] 토론 발언 저장 실패: {speaker_name} (순서: {i + 1})"
                    )
            else:
                logger.warning(
                    f"[CHAT_SERVICE] 잘못된 발언 형식 건너뜀 (순서: {i + 1}): {speech}"
                )

        # 마지막 저장된 메시지의 ID를 assistant_message_id로 설정
        if saved_message_ids:
            assistant_message_id = saved_message_ids[-1]
            chat_channel_service.update_last_message(db, channel_id)
            logger.info(
                f"[CHAT_SERVICE] 토론 응답 저장 완료: {len(saved_message_ids)}개 발언"
            )
            return {
                "assistant_message_id": assistant_message_id,
                "saved_message_ids": saved_message_ids,
            }

        return {}


# 서비스 인스턴스들
chat_channel_service = ChatChannelService()
chat_message_service = ChatMessageService()
