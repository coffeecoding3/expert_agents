"""
LGenie Database Sync Service

Main DB의 채팅 데이터를 LGenie DB에 로깅 목적으로 동기화하는 서비스
"""

import json
import uuid
from datetime import datetime
from logging import getLogger
from typing import Dict, List, Optional, Any, Union, Tuple
from typing_extensions import TypedDict

import httpx
from sqlalchemy.orm import Session

from configs.app_config import load_config
from src.database.connection import get_db, get_lgenie_db
from src.database.models.chat import ChatChannel, ChatMessage
from src.database.models.agent import Agent, AgentLLMConfig
from src.database.models.user import User
from src.database.models.lgenie_models import (
    GenaiChatGroup,
    GenaiChat,
    GenaiChatMessage,
    GenaiChatMessageEventData,
    GenaiChatMessageLink,
    LinkSearchBlock
)
from src.schemas.sse_response import SSEEventType

logger = getLogger("lgenie_sync")

# 상수 정의
MESSAGE_TYPE_USER = "user"
MESSAGE_TYPE_HUMAN = "human"
MESSAGE_TYPE_AI = "ai"
MESSAGE_FILTER_LGE = "LGE"
CHAT_TYPE_PRIVATE = "private"
DELETE_YN_FALSE = 0
DISCUSSION_ORDER_DEFAULT = 999999
TITLE_API_TIMEOUT = 30.0
DATE_FORMAT = "%Y%m%d%H%M%S"

# 토론 관련 상수
DISCUSSION_STAGE_UNKNOWN = "unknown"
DISCUSSION_TYPE = "discussion"
DISCUSSION_PREFIX = "_discussion_"

# 알려진 에이전트 코드
KNOWN_AGENT_CODES = ["caia", "raih"]


class DiscussionPart(TypedDict):
    """토론 메시지의 각 부분 (setup, speaker 발언, wrapup)"""

    stage: str  # "setup" | "proceed" | "wrapup" | "unknown"
    speaker: Optional[str]  # 발언자 이름 (HOST, 전문가명 등)
    content: str  # 발언 내용
    order: int  # discussion_order
    created_at: Optional[str]  # ISO 형식의 생성 시간


class DiscussionMessage(TypedDict):
    """토론 메시지 구조화된 형태"""

    type: str  # "discussion"
    parts: List[DiscussionPart]  # 토론 메시지 부분들의 리스트


class LGenieSyncService:
    """LGenie DB 동기화 서비스"""

    def __init__(self):
        self._main_db_session = None
        self._lgenie_db_session = None

    # ==================== DB 세션 관리 ====================

    def _get_main_session(self) -> Optional[Session]:
        """Main DB 세션 가져오기 (항상 새 세션)"""
        try:
            return next(get_db())
        except Exception as e:
            logger.error(f"Main DB 세션 생성 실패: {e}")
            return None

    def _get_lgenie_session(self) -> Optional[Session]:
        """LGenie DB 세션 가져오기"""
        try:
            return next(get_lgenie_db())
        except Exception as e:
            logger.error(f"LGenie DB 세션 생성 실패: {e}")
            return None

    def _close_session(self, session: Optional[Session], session_name: str = "DB") -> None:
        """DB 세션 안전하게 종료"""
        if session:
            try:
                session.close()
            except Exception as e:
                logger.error(f"{session_name} 세션 종료 실패: {e}")

    # ==================== 유틸리티 메소드 ====================

    def _get_agent_code(self, agent_id: int) -> Optional[str]:
        """에이전트 코드 가져오기"""
        main_db = self._get_main_session()
        if not main_db:
            return None

        try:
            agent = main_db.query(Agent).filter(Agent.id == agent_id).first()
            return agent.code if agent else None
        except Exception as e:
            logger.error(f"에이전트 코드 조회 실패: {e}")
            return None
        finally:
            self._close_session(main_db, "Main DB")

    def _get_actual_user_id(self, main_db: Session, user_id: int) -> str:
        """실제 user_id 조회"""
        user = main_db.query(User).filter(User.id == user_id).first()
        return user.user_id if user else str(user_id)

    def _get_all_agent_codes(self, main_db: Optional[Session] = None) -> List[str]:
        """agents 테이블에서 모든 agent code 조회
        
        Args:
            main_db: Main DB 세션 (없으면 새로 생성)
        
        Returns:
            agent code 리스트 (소문자)
        """
        created_session = False
        if main_db is None:
            main_db = self._get_main_session()
            created_session = True
        
        if not main_db:
            # DB 세션을 가져올 수 없으면 기존 상수 사용
            return KNOWN_AGENT_CODES
        
        try:
            agents = main_db.query(Agent).filter(Agent.is_active == True).all()
            agent_codes = [agent.code.lower() for agent in agents if agent.code]
            return agent_codes if agent_codes else KNOWN_AGENT_CODES
        except Exception as e:
            logger.warning(f"에이전트 코드 목록 조회 실패, 기본값 사용: {e}")
            return KNOWN_AGENT_CODES
        finally:
            if created_session:
                self._close_session(main_db, "Main DB")

    def _convert_message_type(
        self, 
        message_type: Optional[str], 
        message_metadata: Optional[dict] = None, 
        agent_code: Optional[str] = None,
        main_db: Optional[Session] = None
    ) -> str:
        """메시지 타입 변환
        
        Args:
            message_type: 원본 메시지 타입
            message_metadata: 메시지 메타데이터 (선택사항)
            agent_code: 에이전트 코드 (선택사항)
            main_db: Main DB 세션 (선택사항, agent code 조회용)
        
        Returns:
            변환된 메시지 타입 ("human" 또는 "ai")
        """
        if message_type == MESSAGE_TYPE_USER:
            return MESSAGE_TYPE_HUMAN
        
        if not message_type:
            return message_type or ""
        
        if DISCUSSION_PREFIX in message_type:
            return MESSAGE_TYPE_AI
        
        # 공백 제거 및 소문자 변환
        message_type_clean = message_type.strip().lower()
        
        # agent_code가 제공된 경우 확인
        if agent_code and message_type_clean == agent_code.lower().strip():
            return MESSAGE_TYPE_AI
        
        # agents 테이블에서 모든 agent code 조회
        all_agent_codes = self._get_all_agent_codes(main_db)
        
        # 소문자 버전 확인
        if message_type_clean in all_agent_codes:
            return MESSAGE_TYPE_AI
        
        # 대문자 버전도 확인 (agents 테이블의 code를 대문자로 변환하여 비교)
        message_type_upper = message_type.strip().upper()
        all_agent_codes_upper = [code.upper() for code in all_agent_codes]
        if message_type_upper in all_agent_codes_upper:
            return MESSAGE_TYPE_AI
        
        return message_type

    def _get_first_user_message(self, channel_id: int) -> Optional[str]:
        """채널의 첫 번째 사용자 메시지 가져오기"""
        main_db = self._get_main_session()
        if not main_db:
            return None

        try:
            first_message = (
                main_db.query(ChatMessage)
                .filter(
                    ChatMessage.channel_id == channel_id,
                    ChatMessage.message_type == MESSAGE_TYPE_USER,
                    ChatMessage.is_deleted == False,
                )
                .order_by(ChatMessage.created_at.asc())
                .first()
            )
            return first_message.content if first_message else None
        except Exception as e:
            logger.error(f"첫 번째 메시지 조회 실패: {e}")
            return None
        finally:
            self._close_session(main_db, "Main DB")

    def _is_discussion_message(self, message: ChatMessage, agent_code: str) -> bool:
        """토론 메시지 여부 확인"""
        if agent_code != "caia":
            return False
        
        metadata_is_discussion = (
            message.message_metadata
            and isinstance(message.message_metadata, dict)
            and message.message_metadata.get("is_discussion", False)
        )
        type_is_discussion = (
            message.message_type
            and isinstance(message.message_type, str)
            and DISCUSSION_PREFIX in message.message_type
        )
        return metadata_is_discussion or type_is_discussion

    def _get_genai_model_name(self, main_db: Session, agent_id: int) -> Optional[str]:
        """agent_llm_config에서 deployment 값 조회"""
        try:
            agent_llm_config = (
                main_db.query(AgentLLMConfig)
                .filter(AgentLLMConfig.agent_id == agent_id, AgentLLMConfig.is_active == True)
                .first()
            )
            if agent_llm_config and agent_llm_config.config_json:
                deployment = agent_llm_config.config_json.get("deployment")
                if deployment:
                    logger.info(f"deployment 값 조회 완료: agent_id={agent_id}, deployment={deployment}")
                    return deployment
            logger.debug(f"agent_llm_config를 찾을 수 없거나 deployment 값이 없습니다: agent_id={agent_id}")
        except Exception as e:
            logger.warning(f"deployment 값 조회 중 오류 발생: {e}")
        return None

    def _generate_message_group_id(self, message: ChatMessage, converted_type: str) -> str:
        """message_group_id 생성 (deterministic UUID)"""
        if converted_type == MESSAGE_TYPE_HUMAN:
            group_key = f"message_{message.id}"
        elif message.parent_message_id:
            group_key = f"message_{message.parent_message_id}"
        else:
            group_key = f"message_{message.id}"
        
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, group_key))

    # ==================== 채널 동기화 ====================

    def _create_chat_group(
        self, lgenie_db: Session, channel: ChatChannel, actual_user_id: str, first_msg: Optional[str]
    ) -> None:
        """GenaiChatGroup 생성"""
        chat_group = GenaiChatGroup(
            chat_group_id=channel.session_id,
            chat_type=CHAT_TYPE_PRIVATE,
            title=channel.title,
            first_msg=first_msg,
            delete_yn=DELETE_YN_FALSE,
            write_date=channel.created_at.strftime(DATE_FORMAT) if channel.created_at else None,
            creation_user_id=actual_user_id,
            creation_date=channel.created_at or datetime.now(),
            last_update_user_id=actual_user_id,
            last_update_date=channel.updated_at or datetime.now(),
        )
        lgenie_db.add(chat_group)
        lgenie_db.flush()

    def _create_chat(
        self, lgenie_db: Session, session_id: str, agent_code: str, actual_user_id: str, created_at: datetime, updated_at: datetime
    ) -> str:
        """GenaiChat 생성"""
        chat_id = str(uuid.uuid4())
        chat = GenaiChat(
            chat_id=chat_id,
            chat_group_id=session_id,
            conversation_id=None,
            chat_filter=f"{agent_code.upper()}_AGENT",
            message_filter=MESSAGE_FILTER_LGE,
            file_document_id=None,
            creation_user_id=actual_user_id,
            creation_date=created_at or datetime.now(),
            last_update_user_id=actual_user_id,
            last_update_date=updated_at or datetime.now(),
        )
        lgenie_db.add(chat)
        return chat_id

    def sync_chat_channel(self, channel_id: int) -> bool:
        """채팅 채널을 LGenie DB에 동기화"""
        logger.info(f"채널 동기화 시작: channel_id={channel_id}")

        main_db = self._get_main_session()
        lgenie_db = self._get_lgenie_session()

        if not main_db or not lgenie_db:
            logger.error("DB 세션을 가져올 수 없습니다")
            return False

        try:
            channel = main_db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
            if not channel:
                logger.warning(f"채널을 찾을 수 없습니다: {channel_id}")
                return False

            logger.info(
                f"채널 정보 조회 완료: session_id={channel.session_id}, "
                f"user_id={channel.user_id}, agent_id={channel.agent_id}"
            )

            actual_user_id = self._get_actual_user_id(main_db, channel.user_id)
            agent_code = self._get_agent_code(channel.agent_id)
            if not agent_code:
                logger.warning(f"에이전트 코드를 찾을 수 없습니다: {channel.agent_id}")
                return False

            first_msg = self._get_first_user_message(channel_id)

            # GenaiChatGroup 생성 (없는 경우)
            existing_chat_group = (
                lgenie_db.query(GenaiChatGroup)
                .filter(GenaiChatGroup.chat_group_id == channel.session_id)
                .first()
            )
            if not existing_chat_group:
                logger.info(f"GenaiChatGroup 생성: chat_group_id={channel.session_id}")
                self._create_chat_group(lgenie_db, channel, actual_user_id, first_msg)

            # GenaiChat 생성 (없는 경우)
            existing_chat = (
                lgenie_db.query(GenaiChat)
                .filter(GenaiChat.chat_group_id == channel.session_id)
                .first()
            )
            if not existing_chat:
                chat_id = self._create_chat(
                    lgenie_db,
                    channel.session_id,
                    agent_code,
                    actual_user_id,
                    channel.created_at or datetime.now(),
                    channel.updated_at or datetime.now(),
                )
                logger.info(f"GenaiChat 생성 완료: chat_id={chat_id}")

            lgenie_db.commit()
            logger.info(f"채널 동기화 완료: channel_id={channel_id}")
            return True

        except Exception as e:
            logger.error(f"채널 동기화 실패: {e}", exc_info=True)
            if lgenie_db:
                lgenie_db.rollback()
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")
            self._close_session(main_db, "Main DB")

    # ==================== 메시지 동기화 ====================

    def _get_channel_info(self, main_db: Session, channel_id: int) -> Optional[Tuple[ChatChannel, str, str]]:
        """채널 정보 조회 및 검증"""
        channel = main_db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
        if not channel:
            logger.warning(f"채널을 찾을 수 없습니다: {channel_id}")
            return None

        actual_user_id = self._get_actual_user_id(main_db, channel.user_id)
        agent_code = self._get_agent_code(channel.agent_id)
        if not agent_code:
            logger.warning(f"에이전트 코드를 찾을 수 없습니다: {channel.agent_id}")
            return None

        return channel, actual_user_id, agent_code

    def _ensure_lgenie_chat_exists(
        self, lgenie_db: Session, session_id: str, actual_user_id: str, agent_code: str, created_at: datetime, updated_at: datetime
    ) -> Optional[GenaiChat]:
        """LGenie Chat 존재 확인 및 생성"""
        lgenie_chat = (
            lgenie_db.query(GenaiChat)
            .filter(GenaiChat.chat_group_id == session_id)
            .first()
        )
        
        if not lgenie_chat:
            logger.info(f"LGenie 채팅 없음 - 선행 조건 보장 시도: {session_id}")
            self.ensure_lgenie_prereqs(
                session_id, actual_user_id, agent_code, created_at, updated_at, "ensure_group_and_chat"
            )
            lgenie_chat = (
                lgenie_db.query(GenaiChat)
                .filter(GenaiChat.chat_group_id == session_id)
                .first()
            )
            if not lgenie_chat:
                logger.warning(f"LGenie 채팅을 찾을 수 없습니다(보장 후에도): {session_id}")
                return None
        
        return lgenie_chat

    def _check_message_exists(
        self, lgenie_db: Session, chat_id: str, message: ChatMessage, converted_type: str
    ) -> bool:
        """메시지 중복 확인"""
        existing_message = (
            lgenie_db.query(GenaiChatMessage)
            .filter(
                GenaiChatMessage.chat_id == chat_id,
                GenaiChatMessage.message == message.content,
                GenaiChatMessage.message_type == converted_type,
                GenaiChatMessage.creation_date == message.created_at,
            )
            .first()
        )
        
        if existing_message:
            logger.info(
                f"메시지가 이미 존재합니다: existing_message_id={existing_message.message_id}, "
                f"type={converted_type}"
            )
            return True
        return False

    def _extract_token_count(self, message: ChatMessage) -> Optional[int]:
        """메시지에서 토큰 수 추출"""
        if message.message_metadata and isinstance(message.message_metadata, dict):
            return message.message_metadata.get("total_token")
        return None

    # ==================== 토론 메시지 처리 ====================

    def _filter_discussion_messages(self, messages: List[ChatMessage]) -> List[ChatMessage]:
        """토론 메시지만 필터링"""
        discussion_messages = []
        for msg in messages:
            msg_metadata = msg.message_metadata
            if isinstance(msg_metadata, dict):
                if msg_metadata.get("is_discussion", False) or "discussion_order" in msg_metadata:
                    discussion_messages.append(msg)
            elif msg.message_type and DISCUSSION_PREFIX in msg.message_type:
                discussion_messages.append(msg)
        return discussion_messages

    def _sort_discussion_messages(self, messages: List[ChatMessage]) -> List[ChatMessage]:
        """토론 메시지를 discussion_order로 정렬: -1(user) < 0(setup) < 1~N(script) < N+1(wrapup)"""
        messages.sort(
            key=lambda m: (
                m.message_metadata.get("discussion_order", DISCUSSION_ORDER_DEFAULT)
                if isinstance(m.message_metadata, dict)
                else DISCUSSION_ORDER_DEFAULT,
                m.created_at or datetime.min,  # datetime.now() 대신 datetime.min 사용하여 일관성 보장
            )
        )
        return messages

    def _extract_speaker_name(self, message: ChatMessage) -> Optional[str]:
        """메시지에서 speaker_name 추출"""
        if isinstance(message.message_metadata, dict):
            speaker_name = message.message_metadata.get("speaker_name")
            if speaker_name:
                return speaker_name
        
        if message.message_type and DISCUSSION_PREFIX in message.message_type:
            parts = message.message_type.split(DISCUSSION_PREFIX)
            if len(parts) > 1:
                return parts[1]
        
        return None

    def _create_discussion_part(self, message: ChatMessage) -> DiscussionPart:
        """토론 메시지에서 DiscussionPart 생성"""
        stage = DISCUSSION_STAGE_UNKNOWN
        if isinstance(message.message_metadata, dict):
            stage = message.message_metadata.get("stage", DISCUSSION_STAGE_UNKNOWN)
        
        speaker_name = self._extract_speaker_name(message)
        
        content = message.content or ""
        if speaker_name and content.startswith(f"{speaker_name}:"):
            content = content[len(f"{speaker_name}:"):].strip()
        
        discussion_order = (
            message.message_metadata.get("discussion_order", DISCUSSION_ORDER_DEFAULT)
            if isinstance(message.message_metadata, dict)
            else DISCUSSION_ORDER_DEFAULT
        )
        
        return {
            "stage": stage,
            "speaker": speaker_name,
            "content": content,
            "order": discussion_order,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _calculate_total_tokens(self, messages: List[ChatMessage]) -> int:
        """토론 메시지들의 총 토큰 수 계산"""
        total = 0
        for msg in messages:
            if isinstance(msg.message_metadata, dict):
                total += msg.message_metadata.get("total_token", 0)
        return total

    def _sync_discussion_messages(
        self,
        main_db: Session,
        lgenie_db: Session,
        message: ChatMessage,
        lgenie_chat: GenaiChat,
        message_group_id: str,
        actual_user_id: str,
        agent_code: str,
        genai_model_name: Optional[str],
    ) -> bool:
        """토론 메시지 통합 동기화"""
        if not message.parent_message_id:
            return False

        parent_user_message = (
            main_db.query(ChatMessage)
            .filter(ChatMessage.id == message.parent_message_id)
            .first()
        )
        if not parent_user_message:
            return False

        # 부모 user 메시지의 LGenie message_id 찾기
        parent_lgenie_user_message = (
            lgenie_db.query(GenaiChatMessage)
            .filter(
                GenaiChatMessage.chat_id == lgenie_chat.chat_id,
                GenaiChatMessage.message == parent_user_message.content,
                GenaiChatMessage.creation_date == parent_user_message.created_at,
            )
            .first()
        )

        # 이미 동기화된 토론 메시지 확인
        existing_discussion = None
        if parent_lgenie_user_message:
            existing_discussion = (
                lgenie_db.query(GenaiChatMessage)
                .filter(
                    GenaiChatMessage.chat_id == lgenie_chat.chat_id,
                    GenaiChatMessage.human_message_id == parent_lgenie_user_message.message_id,
                    GenaiChatMessage.message_type == MESSAGE_TYPE_AI,
                )
                .first()
            )

        if existing_discussion:
            logger.info(f"토론 메시지가 이미 동기화됨: parent_message_id={message.parent_message_id}")
            return True

        # 같은 parent_message_id를 가진 모든 토론 메시지 조회
        all_discussion_messages = (
            main_db.query(ChatMessage)
            .filter(
                ChatMessage.channel_id == message.channel_id,
                ChatMessage.parent_message_id == message.parent_message_id,
                ChatMessage.is_deleted == False,
            )
            .all()
        )

        discussion_messages = self._filter_discussion_messages(all_discussion_messages)
        discussion_messages = self._sort_discussion_messages(discussion_messages)

        if not discussion_messages:
            logger.warning(f"토론 메시지를 찾을 수 없음: parent_message_id={message.parent_message_id}")
            return True

        # 토론 메시지 통합
        logger.info(
            f"토론 메시지 통합 시작: parent_message_id={message.parent_message_id}, "
            f"토론 메시지 수={len(discussion_messages)}"
        )

        discussion_parts = [self._create_discussion_part(msg) for msg in discussion_messages]
        # discussion_parts를 order 필드로 다시 정렬하여 순서 보장
        discussion_parts.sort(key=lambda p: (p.get("order", DISCUSSION_ORDER_DEFAULT), p.get("created_at") or ""))
        total_tokens = self._calculate_total_tokens(discussion_messages)

        structured_message: DiscussionMessage = {
            "type": DISCUSSION_TYPE,
            "parts": discussion_parts,
        }
        combined_content = json.dumps(structured_message, ensure_ascii=False, indent=2)

        human_message_id = (
            parent_lgenie_user_message.message_id if parent_lgenie_user_message else None
        )

        # creation_date는 정렬된 메시지 중 가장 작은 discussion_order를 가진 메시지(setup, order=0)의 updated_at 사용
        # setup 메시지 찾기 (discussion_order = 0)
        setup_message = None
        for msg in discussion_messages:
            if (
                isinstance(msg.message_metadata, dict)
                and msg.message_metadata.get("discussion_order") == 0
            ):
                setup_message = msg
                break
        
        # setup이 없으면 첫 번째 메시지 사용
        creation_date_msg = setup_message if setup_message else discussion_messages[0]
        creation_date = creation_date_msg.updated_at or datetime.now()
        
        # last_update_date는 마지막 메시지(wrapup)의 updated_at 사용
        last_update_date = discussion_messages[-1].updated_at or datetime.now()

        logger.info(
            f"토론 메시지 creation_date 설정: setup_message={setup_message is not None}, "
            f"creation_date={creation_date}, last_update_date={last_update_date}"
        )

        # 통합된 토론 메시지 저장
        lgenie_message_id = str(uuid.uuid4())
        lgenie_message = GenaiChatMessage(
            message_id=lgenie_message_id,
            chat_id=lgenie_chat.chat_id,
            message_group_id=message_group_id,
            message_filter=MESSAGE_FILTER_LGE,
            message_type=MESSAGE_TYPE_AI,
            message=combined_content,
            token_count=total_tokens if total_tokens > 0 else None,
            response_second=None,
            message_result=1,  # AI 메시지는 1
            planner_result=None,
            response_message=None,
            generator_type=None,
            link_count=None,
            genai_model_id=None,
            genai_model_name=genai_model_name,
            genai_model_display_name=None,
            retriever_id=None,
            retriever_name=None,
            retriever_deploy_name=None,
            deployment_name=None,
            search_scope=None,
            chat_filter=f"{agent_code.upper()}_AGENT",
            human_message_id=human_message_id,
            creation_user_id=actual_user_id,
            creation_date=creation_date,  # setup 메시지의 created_at 사용
            last_update_user_id=actual_user_id,
            last_update_date=last_update_date,
        )

        try:
            lgenie_db.add(lgenie_message)
            lgenie_db.commit()
            logger.info(
                f"토론 메시지 통합 완료: message_id={lgenie_message_id}, "
                f"parts_count={len(discussion_parts)}, human_message_id={human_message_id}"
            )
            return True
        except Exception as e:
            logger.error(f"토론 메시지 통합 저장 실패: {e}", exc_info=True)
            lgenie_db.rollback()
            return False

    # ==================== 이벤트 데이터 저장 ====================

    def _save_discussion_event_data(
        self, lgenie_db: Session, message: ChatMessage, lgenie_message_id: str, actual_user_id: str
    ) -> None:
        """토론 메시지 event_data 저장"""
        if not message.message_type or DISCUSSION_PREFIX not in message.message_type:
            return

        try:
            parts = message.message_type.split(DISCUSSION_PREFIX)
            if len(parts) < 2:
                logger.warning(f"토론 메시지 타입 파싱 실패: message_type={message.message_type}")
                return

            speaker_name = parts[1]
            from src.schemas.sse_response import MultiLLMEventData
            
            event_data_obj = MultiLLMEventData(context="DISCUSSION", llm_role=speaker_name)
            event_data_json = event_data_obj.model_dump()
            
            event_data_record = GenaiChatMessageEventData(
                message_id=lgenie_message_id,
                event_type=SSEEventType.MULTI_LLM,
                event_data=event_data_json,
                creation_user_id=actual_user_id,
                creation_date=message.created_at or datetime.now(),
                last_update_user_id=actual_user_id,
                last_update_date=message.updated_at or datetime.now(),
            )
            
            lgenie_db.add(event_data_record)
            lgenie_db.commit()
            logger.info(
                f"토론 메시지 event_data 저장 완료: message_id={lgenie_message_id}, "
                f"speaker_name={speaker_name}, event_type={SSEEventType.MULTI_LLM}"
            )
        except Exception as e:
            logger.error(f"토론 메시지 event_data 저장 중 오류: {e}", exc_info=True)

    def _save_event_data(
            self, lgenie_db: Session, message: ChatMessage, state, lgenie_message_id: str, actual_user_id: str
    ) -> None:
        """메시지 event_data 저장"""
        if not message.message_type or message.message_type != "RAIH":
            return
        if state.get("intent") == 'general_question':
            return

        try:
            from src.schemas.sse_response import RetrievedDocumentsEventData

            event_data_obj = RetrievedDocumentsEventData(documents=state.get("links", []))
            event_data_json = event_data_obj.model_dump()

            event_data_record = GenaiChatMessageEventData(
                message_id=lgenie_message_id,
                event_type=SSEEventType.RETRIEVED_DOCUMENTS,
                event_data=event_data_json,
                creation_user_id=actual_user_id,
                creation_date=message.created_at or datetime.now(),
                last_update_user_id=actual_user_id,
                last_update_date=message.updated_at or datetime.now(),
            )

            lgenie_db.add(event_data_record)
            lgenie_db.commit()
            logger.info(
                f"메시지 event_data 저장 완료: message_id={lgenie_message_id}"
            )
        except Exception as e:
            logger.error(f"메시지 event_data 저장 중 오류: {e}", exc_info=True)


    def _save_links(self, lgenie_db: Session, message: ChatMessage, state, lgenie_message_id: str, actual_user_id: str
                    ) -> None:
        """메시지 event_data 저장"""
        if not message.message_type or message.message_type != "RAIH":
            return


    def _save_topic_suggestions_event_data(
        self, lgenie_db: Session, message: ChatMessage, lgenie_message_id: str, actual_user_id: str
    ) -> None:
        """topic_suggestions event_data 저장"""
        if not message.message_metadata or not isinstance(message.message_metadata, dict):
            return

        topic_suggestions = message.message_metadata.get("topic_suggestions")
        if not topic_suggestions or not isinstance(topic_suggestions, list) or len(topic_suggestions) == 0:
            return

        try:
            event_data_json = {"questions": topic_suggestions}
            event_data_record = GenaiChatMessageEventData(
                message_id=lgenie_message_id,
                event_type=SSEEventType.QUESTION_SUGGEST,
                event_data=event_data_json,
                creation_user_id=actual_user_id,
                creation_date=message.created_at or datetime.now(),
                last_update_user_id=actual_user_id,
                last_update_date=message.updated_at or datetime.now(),
            )
            
            lgenie_db.add(event_data_record)
            lgenie_db.commit()
            logger.info(
                f"topic_suggestions event_data 저장 완료: message_id={lgenie_message_id}, "
                f"questions_count={len(topic_suggestions)}, event_type={SSEEventType.QUESTION_SUGGEST}"
            )
        except Exception as e:
            logger.error(f"topic_suggestions event_data 저장 중 오류: {e}", exc_info=True)

    # ==================== 일반 메시지 동기화 ====================

    def _create_lgenie_message(
        self,
        message: ChatMessage,
        lgenie_chat: GenaiChat,
        message_group_id: str,
        converted_type: str,
        state,
        token_count: Optional[int],
        genai_model_name: Optional[str],
        agent_code: str,
        actual_user_id: str,
        human_message_id: Optional[str] = None,
    ) -> GenaiChatMessage:
        """GenaiChatMessage 객체 생성"""
        lgenie_message_id = str(uuid.uuid4())
        # message_type에 따라 message_result 설정
        message_result = 1 if converted_type == MESSAGE_TYPE_AI else (0 if converted_type == MESSAGE_TYPE_HUMAN else None)
        genai_chat_message = GenaiChatMessage(
            message_id=lgenie_message_id,
            chat_id=lgenie_chat.chat_id,
            message_group_id=message_group_id,
            message_filter=MESSAGE_FILTER_LGE,
            message_type=converted_type,
            message=message.content,
            token_count=token_count,
            response_second=None,
            message_result=message_result,
            planner_result=None,
            response_message=None,
            generator_type=None,
            link_count=None,
            genai_model_id=None,
            genai_model_name=genai_model_name,
            genai_model_display_name=None,
            retriever_id=None,
            retriever_name=None,
            retriever_deploy_name=None,
            deployment_name=None,
            search_scope=None,
            chat_filter=f"{agent_code.upper()}_AGENT",
            human_message_id=human_message_id,
            creation_user_id=actual_user_id,
            creation_date=message.created_at or datetime.now(),
            last_update_user_id=actual_user_id,
            last_update_date=message.updated_at or datetime.now()
        )
        if converted_type != MESSAGE_TYPE_HUMAN:
            links_data = []
            if isinstance(state, dict):
                links_data = state.get("links", [])

            if links_data:
                for link in links_data:
                    link["link_search_blocks"] = [{
                        "selector": None,
                        "block": link.get("context"),
                        "score": link.get("score")
                    }]

                genai_chat_message.links = [
                    GenaiChatMessageLink(
                        chat_message=genai_chat_message,
                        file_document_id=link.get("file_document_id", ""),
                        filename=link.get("filename", ""),
                        type=link.get("type", "D"),
                        title=link.get("title"),
                        extension=link.get("extension", ""),
                        description=link.get("description", ""),
                        expire_date=link.get("expire_date", "9999-12-31"),
                        user_id=link.get("system_code", ""),
                        lgss_title=link.get("lgss_title", ""),
                        view_url=link.get("view_url", " "),
                        match_yn = link.get("match_yn", None),
                        creation_date = datetime.now(),
                        last_update_date = datetime.now(),
                        creation_user_id = actual_user_id,
                        last_update_user_id = actual_user_id,
                        area=link.get("area", ""),
                        link_search_blocks=[
                            LinkSearchBlock(
                                selector=link_search_block.get("selector", ""),
                                block=link_search_block.get("block", ""),
                                score=link_search_block.get("score", ""),
                                creation_date = datetime.now(),
                                last_update_date = datetime.now(),
                                creation_user_id = actual_user_id,
                                last_update_user_id = actual_user_id,

                            ) for link_search_block in link.get("link_search_blocks", [])
                        ]
                    ) for link in links_data
                ]
                logger.info(
                    f"메시지 links 추가 완료: message_id={lgenie_message_id}"
                )

        return genai_chat_message

    def sync_chat_message(
        self, message: Union[ChatMessage, int], state, main_db: Optional[Session] = None
    ) -> bool:
        """채팅 메시지를 LGenie DB에 동기화"""
        created_main_session = False
        if main_db is None:
            main_db = self._get_main_session()
            created_main_session = True
        
        lgenie_db = self._get_lgenie_session()

        if not main_db or not lgenie_db:
            logger.error("DB 세션을 가져올 수 없습니다")
            return False

        try:
            # 메시지 객체 조회 (ID인 경우)
            if isinstance(message, int):
                message_id = message
                message = main_db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
                if not message:
                    logger.error(f"메시지를 찾을 수 없습니다: message_id={message_id}")
                    return False

            logger.info(f"메시지 동기화 시작: message_id={message.id}")

            # 채널 정보 조회
            channel_info = self._get_channel_info(main_db, message.channel_id)
            if not channel_info:
                return False
            
            channel, actual_user_id, agent_code = channel_info

            # LGenie Chat 확인 및 생성
            lgenie_chat = self._ensure_lgenie_chat_exists(
                lgenie_db,
                channel.session_id,
                actual_user_id,
                agent_code,
                message.created_at or datetime.now(),
                message.updated_at or datetime.now(),
            )
            if not lgenie_chat:
                return False

            # 메시지 타입 변환
            converted_type = self._convert_message_type(
                message.message_type, message.message_metadata, agent_code=agent_code, main_db=main_db
            )

            # 중복 확인
            if self._check_message_exists(lgenie_db, lgenie_chat.chat_id, message, converted_type):
                return True

            # 토큰 수 및 모델명 조회
            token_count = self._extract_token_count(message)
            genai_model_name = self._get_genai_model_name(main_db, message.agent_id)

            # 토론 메시지 여부 확인
            is_discussion = self._is_discussion_message(message, agent_code)

            # message_group_id 생성
            message_group_id = self._generate_message_group_id(message, converted_type)

            # 토론 메시지 처리
            if is_discussion and message.parent_message_id:
                return self._sync_discussion_messages(
                    main_db,
                    lgenie_db,
                    message,
                    lgenie_chat,
                    message_group_id,
                    actual_user_id,
                    agent_code,
                    genai_model_name,
                )

            # 일반 메시지 저장
            lgenie_message = self._create_lgenie_message(
                message,
                lgenie_chat,
                message_group_id,
                converted_type,
                state,
                token_count,
                genai_model_name,
                agent_code,
                actual_user_id,
            )

            lgenie_db.add(lgenie_message)
            lgenie_db.commit()
            logger.info(
                f"메시지 동기화 완료: main_message_id={message.id} -> "
                f"lgenie_message_id={lgenie_message.message_id}, type={converted_type}"
            )

            # 이벤트 데이터 저장
            self._save_event_data(lgenie_db, message, state, lgenie_message.message_id, actual_user_id)
            #self._save_links(lgenie_db, message, state, lgenie_message.message_id, actual_user_id)
            self._save_discussion_event_data(lgenie_db, message, lgenie_message.message_id, actual_user_id)
            self._save_topic_suggestions_event_data(lgenie_db, message, lgenie_message.message_id, actual_user_id)

            return True

        except Exception as e:
            logger.error(f"메시지 동기화 실패: {e}", exc_info=True)
            if lgenie_db:
                lgenie_db.rollback()
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")
            if created_main_session:
                self._close_session(main_db, "Main DB")

    # ==================== 채널 전체 동기화 ====================

    def _get_sorted_messages(self, main_db: Session, channel_id: int) -> List[ChatMessage]:
        """채널의 모든 메시지 조회 및 정렬: -1(user) < 0(setup) < 1~N(script) < N+1(wrapup)"""
        messages = (
            main_db.query(ChatMessage)
            .filter(ChatMessage.channel_id == channel_id, ChatMessage.is_deleted == False)
            .all()
        )

        def get_sort_key(msg: ChatMessage) -> tuple:
            """정렬 키 생성"""
            metadata = msg.message_metadata
            if metadata and isinstance(metadata, dict):
                discussion_order = metadata.get("discussion_order")
                if discussion_order is not None and isinstance(discussion_order, int):
                    return (discussion_order, msg.created_at or datetime.min)
            return (DISCUSSION_ORDER_DEFAULT, msg.created_at or datetime.min)

        return sorted(messages, key=get_sort_key)

    def sync_channel_with_messages(self, channel_id: int, state) -> bool:
        """채널과 모든 메시지를 함께 동기화"""
        logger.info(f"채널 전체 동기화 시작: channel_id={channel_id}")

        main_db = self._get_main_session()
        if not main_db:
            logger.error("Main DB 세션을 가져올 수 없습니다")
            return False

        try:
            # 1단계: 채널 동기화
            logger.info("1단계: 채널 동기화 시작")
            if not self.sync_chat_channel(channel_id):
                logger.error(f"채널 동기화 실패: {channel_id}")
                return False

            # 2단계: 메시지 조회 및 정렬
            logger.info("2단계: 채널의 모든 메시지 조회")
            messages = self._get_sorted_messages(main_db, channel_id)
            
            if not messages:
                logger.info(f"동기화할 메시지가 없습니다: {channel_id}")
                return True

            # 메시지 타입별 통계 로깅
            message_type_counts = {}
            for msg in messages:
                msg_type = msg.message_type or "unknown"
                message_type_counts[msg_type] = message_type_counts.get(msg_type, 0) + 1
            logger.info(f"조회된 메시지 수: {len(messages)}, 타입별 통계: {message_type_counts}")

            # 3단계: 메시지 동기화
            logger.info("3단계: 메시지 동기화 시작")
            success_count = 0
            failed_messages = []

            for i, message in enumerate(messages, 1):
                try:
                    if self.sync_chat_message(message, state, main_db):
                        success_count += 1
                        logger.info(f"메시지 동기화 성공: {i}/{len(messages)} - message_id={message.id}")
                    else:
                        failed_messages.append(message.id)
                        logger.warning(
                            f"메시지 동기화 실패: {i}/{len(messages)} - message_id={message.id}, "
                            f"message_type={message.message_type}"
                        )
                except Exception as e:
                    failed_messages.append(message.id)
                    logger.error(
                        f"메시지 동기화 중 예외 발생: {i}/{len(messages)} - message_id={message.id}, "
                        f"message_type={message.message_type}, error={e}",
                        exc_info=True,
                    )

            logger.info(f"채널 전체 동기화 완료: {channel_id}, 메시지 {success_count}/{len(messages)}")
            if failed_messages:
                logger.warning(f"실패한 메시지들: {failed_messages}")

            sync_success = success_count == len(messages)

            # 4단계: first_msg 업데이트
            if sync_success:
                logger.info("4단계: first_msg 업데이트 시작")
                try:
                    channel = main_db.query(ChatChannel).filter(ChatChannel.id == channel_id).first()
                    if channel and channel.session_id:
                        update_success = self.update_chat_group_first_msg_and_title(
                            channel.session_id, channel_id
                        )
                        if update_success:
                            logger.info(f"first_msg 업데이트 완료: session_id={channel.session_id}")
                        else:
                            logger.warning(f"first_msg 업데이트 실패: session_id={channel.session_id}")
                    else:
                        logger.warning(f"채널 또는 session_id를 찾을 수 없습니다: channel_id={channel_id}")
                except Exception as e:
                    logger.error(f"first_msg 업데이트 중 예외 발생: {e}", exc_info=True)

            return sync_success

        except Exception as e:
            logger.error(f"채널 전체 동기화 실패: {e}", exc_info=True)
            return False
        finally:
            self._close_session(main_db, "Main DB")

    # ==================== 기타 메소드 ====================

    def ensure_lgenie_prereqs(
        self,
        session_id: str,
        creation_user_id: str,
        agent_code: str,
        created_at: datetime,
        updated_at: datetime,
        mode: str,
    ) -> bool:
        """LGenie 선행 조건 보장
        
        Modes:
          - "verify_only": require GenaiChatGroup exists, do nothing else
          - "ensure_chat": require GenaiChatGroup exists; create GenaiChat if missing
          - "ensure_group_and_chat": create GenaiChatGroup and GenaiChat if missing
        """
        lgenie_db = self._get_lgenie_session()
        if not lgenie_db:
            logger.error("LGenie DB 세션을 가져올 수 없습니다")
            return False

        try:
            # Group check/create
            group = (
                lgenie_db.query(GenaiChatGroup)
                .filter(GenaiChatGroup.chat_group_id == session_id)
                .first()
            )

            if not group:
                logger.info(f"GenaiChatGroup 생성: chat_group_id={session_id}")
                group = GenaiChatGroup(
                    chat_group_id=session_id,
                    chat_type=CHAT_TYPE_PRIVATE,
                    title=f"채팅 {session_id[:8]}...",
                    first_msg=None,
                    delete_yn=DELETE_YN_FALSE,
                    write_date=created_at.strftime(DATE_FORMAT) if created_at else None,
                    creation_user_id=creation_user_id,
                    creation_date=created_at or datetime.now(),
                    last_update_user_id=creation_user_id,
                    last_update_date=updated_at or datetime.now(),
                )
                lgenie_db.add(group)
                lgenie_db.flush()

            # Chat check/create
            chat = (
                lgenie_db.query(GenaiChat)
                .filter(GenaiChat.chat_group_id == session_id)
                .first()
            )

            if not chat:
                self._create_chat(lgenie_db, session_id, agent_code, creation_user_id, created_at, updated_at)

            lgenie_db.commit()
            return True
        except Exception as e:
            logger.error(f"ensure_lgenie_prereqs 실패: {e}", exc_info=True)
            lgenie_db.rollback()
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")

    def check_chat_group_exists(self, chat_group_id: str) -> bool:
        """LGenie DB에서 chat_group_id 존재 여부 확인"""
        logger.info(f"LGenie DB chat_group 존재 여부 확인 시작: {chat_group_id}")

        lgenie_db = self._get_lgenie_session()
        if not lgenie_db:
            logger.error("LGenie DB 세션을 가져올 수 없습니다")
            return False

        try:
            chat_group = (
                lgenie_db.query(GenaiChatGroup)
                .filter(GenaiChatGroup.chat_group_id == chat_group_id)
                .first()
            )
            exists = chat_group is not None
            logger.info(
                f"LGenie DB chat_group 확인 완료: {chat_group_id} - "
                f"{'존재함' if exists else '존재하지 않음'}"
            )
            return exists
        except Exception as e:
            logger.error(f"LGenie DB chat_group 조회 실패: {e}")
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")

    def _get_session_token(self, endpoint: str, ssolgenet_exa: Optional[str] = None) -> Optional[str]:
        """세션 토큰 발급"""
        if not ssolgenet_exa:
            logger.warning("[SESSION API] ssolgenet_exa 값이 없어 세션 발급을 건너뜁니다.")
            return None
        
        try:
            session_url = f"{endpoint.rstrip('/')}/api/v4/auth/session"
            logger.info(f"[SESSION API] 세션 발급 요청: url={session_url}")
            
            headers = {
                "accept": "application/json",
                "x-ssolgenet-exa": ssolgenet_exa,
                "Content-Type": "application/json",
            }
            cookies = {
                "ssolgenet_exa": ssolgenet_exa,
            }
            
            with httpx.Client(timeout=TITLE_API_TIMEOUT) as client:
                response = client.post(session_url, headers=headers, cookies=cookies, json={})
                logger.info(f"[SESSION API] 응답 수신: status_code={response.status_code}")
                
                response.raise_for_status()
                response_data = response.json()
                logger.info(f"[SESSION API] 응답 데이터: {response_data}")
                
                # 세션 토큰 추출 (응답 형식에 따라 수정 필요)
                if response_data.get("status") is True and "data" in response_data:
                    session_token = response_data.get("data", {}).get("session_token") or response_data.get("data", {}).get("token")
                    if session_token:
                        logger.info(f"[SESSION API] 세션 토큰 발급 성공")
                        return session_token
                    else:
                        logger.warning(f"[SESSION API] 세션 토큰을 찾을 수 없습니다. 응답: {response_data}")
                else:
                    logger.warning(f"[SESSION API] 세션 발급 실패. 응답: {response_data}")
                return None
        except httpx.HTTPError as e:
            status_code = "N/A"
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            logger.error(
                f"[SESSION API] HTTP 에러 발생: error={e}, status_code={status_code}",
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(f"[SESSION API] 예외 발생: error={e}", exc_info=True)
            return None

    def _fetch_title_from_api(self, session_id: str, ssolgenet_exa: Optional[str] = None) -> Optional[str]:
        """API에서 title 가져오기"""
        logger.info(f"[TITLE API] title 조회 시작: session_id={session_id}")
        
        try:
            config = load_config()
            lgenie_backend_config = config.get("lgenie_backend", {})
            endpoint = lgenie_backend_config.get("endpoint")
            
            logger.info(f"[TITLE API] 설정 확인: endpoint={endpoint}")
            
            if not endpoint:
                logger.warning("[TITLE API] lgenie_backend.endpoint가 설정되지 않았습니다. title 업데이트를 건너뜁니다.")
                return None

            # 세션 토큰 발급
            session_token = self._get_session_token(endpoint, ssolgenet_exa)
            if not session_token:
                logger.warning("[TITLE API] 세션 토큰 발급 실패로 title 조회를 건너뜁니다.")
                return None

            title_url = f"{endpoint.rstrip('/')}/api/v4/channels/{session_id}/title"
            logger.info(f"[TITLE API] 요청 URL: {title_url}")
            
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {session_token}",  # 또는 적절한 헤더 형식
            }
            if ssolgenet_exa:
                headers["x-ssolgenet-exa"] = ssolgenet_exa
                cookies = {"ssolgenet_exa": ssolgenet_exa}
            else:
                cookies = {}
            
            logger.info(f"[TITLE API] 요청 헤더: {headers}")
            
            with httpx.Client(timeout=TITLE_API_TIMEOUT) as client:
                logger.info(f"[TITLE API] POST 요청 전송: url={title_url}")
                response = client.post(title_url, headers=headers, cookies=cookies, json={})
                logger.info(f"[TITLE API] 응답 수신: status_code={response.status_code}")
                
                response.raise_for_status()
                response_data = response.json()
                logger.info(f"[TITLE API] 응답 데이터: {response_data}")
                
                status = response_data.get("status")
                has_data = "data" in response_data
                has_title = has_data and "title" in response_data.get("data", {})
                
                logger.info(
                    f"[TITLE API] 응답 검증: status={status}, has_data={has_data}, has_title={has_title}"
                )
                
                if status is True and has_data and has_title:
                    title = response_data["data"]["title"]
                    logger.info(f"[TITLE API] title 추출 성공: title={title}")
                    return title
                else:
                    logger.warning(
                        f"[TITLE API] title API 응답 형식이 예상과 다릅니다. "
                        f"status={status}, has_data={has_data}, has_title={has_title}, "
                        f"response_data={response_data}"
                    )
                    return None
        except httpx.HTTPError as e:
            status_code = "N/A"
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
            logger.error(
                f"[TITLE API] HTTP 에러 발생: session_id={session_id}, "
                f"error={e}, status_code={status_code}",
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"[TITLE API] 예외 발생: session_id={session_id}, error={e}",
                exc_info=True
            )
            return None

    def update_chat_group_first_msg_and_title(
        self, session_id: str, channel_id: int, ssolgenet_exa: Optional[str] = None
    ) -> bool:
        """LGenie DB의 genai_chat_group 테이블에서 first_msg를 업데이트
        
        Args:
            session_id: 채팅 그룹 ID (session_id)
            channel_id: Main DB의 채널 ID (첫 user_query 조회용)
            ssolgenet_exa: SSO 쿠키 값 (사용하지 않음, 호환성을 위해 유지)
        """
        logger.info(
            f"채팅 그룹 first_msg 업데이트 시작: session_id={session_id}, channel_id={channel_id}"
        )

        lgenie_db = self._get_lgenie_session()
        if not lgenie_db:
            logger.error("LGenie DB 세션을 가져올 수 없습니다")
            return False

        try:
            chat_group = (
                lgenie_db.query(GenaiChatGroup)
                .filter(GenaiChatGroup.chat_group_id == session_id)
                .first()
            )

            if not chat_group:
                logger.warning(f"채팅 그룹을 찾을 수 없습니다: {session_id}")
                return False

            # first_msg 업데이트
            if chat_group.first_msg is None:
                first_user_query = self._get_first_user_message(channel_id)
                if first_user_query:
                    chat_group.first_msg = first_user_query
                    logger.info(f"first_msg 업데이트: session_id={session_id}, first_msg={first_user_query[:50]}...")
                else:
                    logger.warning(f"첫 user_query를 찾을 수 없습니다: channel_id={channel_id}")

            chat_group.last_update_date = datetime.now()
            lgenie_db.commit()
            logger.info(f"채팅 그룹 first_msg 업데이트 완료: session_id={session_id}")
            return True

        except Exception as e:
            logger.error(f"채팅 그룹 first_msg 업데이트 실패: {e}", exc_info=True)
            if lgenie_db:
                lgenie_db.rollback()
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")

    def update_chat_group_title(self, session_id: str, topic: str) -> bool:
        """LGenie DB의 genai_chat_group 테이블에서 title을 업데이트"""
        logger.info(f"채팅 그룹 제목 업데이트 시작: session_id={session_id}, topic={topic}")

        lgenie_db = self._get_lgenie_session()
        if not lgenie_db:
            logger.error("LGenie DB 세션을 가져올 수 없습니다")
            return False

        try:
            chat_group = (
                lgenie_db.query(GenaiChatGroup)
                .filter(GenaiChatGroup.chat_group_id == session_id)
                .first()
            )

            if not chat_group:
                logger.warning(f"채팅 그룹을 찾을 수 없습니다: {session_id}")
                return False

            new_title = f"토론: {topic}" if topic else "토론"
            chat_group.title = new_title
            chat_group.last_update_date = datetime.now()

            lgenie_db.commit()
            logger.info(f"채팅 그룹 제목 업데이트 완료: {session_id} -> {new_title}")
            return True

        except Exception as e:
            logger.error(f"채팅 그룹 제목 업데이트 실패: {e}", exc_info=True)
            if lgenie_db:
                lgenie_db.rollback()
            return False
        finally:
            self._close_session(lgenie_db, "LGenie DB")

    def close(self):
        """세션 종료"""
        if self._main_db_session:
            self._close_session(self._main_db_session, "Main DB")
            self._main_db_session = None


# 전역 인스턴스
lgenie_sync_service = LGenieSyncService()
