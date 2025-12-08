"""
LGenie Database SQLAlchemy models

LGenie DB는 외부 서비스의 데이터베이스로, 기존 테이블 구조에 맞춰 모델을 정의합니다.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# LGenie DB용 별도 Base 클래스
LGenieBase = declarative_base()


class GenaiChatGroup(LGenieBase):
    """LGenie 채팅 그룹 테이블"""

    __tablename__ = "genai_chat_group"

    chat_group_id = Column(String(225), primary_key=True)
    chat_type = Column(Text, nullable=False)
    title = Column(String(255), nullable=True, comment="채팅방 제목")
    first_msg = Column(Text, nullable=True)
    delete_yn = Column(SmallInteger, nullable=False)
    write_date = Column(String(225), nullable=True)
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    # 관계
    chats = relationship("GenaiChat", back_populates="chat_group")

    # 인덱스
    __table_args__ = (
        Index("idx_genai_chat_group_01", "creation_date", "creation_user_id"),
        Index(
            "idx_chat_group_user_type_del_udate",
            "creation_user_id",
            "chat_type",
            "delete_yn",
            "last_update_date",
            "chat_group_id",
        ),
    )


class GenaiChat(LGenieBase):
    """LGenie 채팅 테이블"""

    __tablename__ = "genai_chat"

    chat_id = Column(String(225), primary_key=True)
    chat_group_id = Column(String(225), ForeignKey("genai_chat_group.chat_group_id"), nullable=False)
    conversation_id = Column(String(225), nullable=True)
    chat_filter = Column(String(225), nullable=True)
    message_filter = Column(String(225), nullable=True)
    file_document_id = Column(String(225), nullable=True)
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    # 관계
    chat_group = relationship("GenaiChatGroup", back_populates="chats")
    messages = relationship("GenaiChatMessage", back_populates="chat")

    # 인덱스
    __table_args__ = (
        Index("chat_group_id", "chat_group_id"),
        Index("file_document_id", "file_document_id"),
    )


class GenaiChatMessage(LGenieBase):
    """LGenie 채팅 메시지 테이블"""

    __tablename__ = "genai_chat_message"

    message_id = Column(String(225), primary_key=True)
    chat_id = Column(String(225), ForeignKey("genai_chat.chat_id"), nullable=False)
    message_group_id = Column(String(225), nullable=True)
    message_filter = Column(String(225), nullable=True)
    message_type = Column(String(225), nullable=True)
    message = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    response_second = Column(Float, nullable=True)
    message_result = Column(SmallInteger, nullable=True)
    planner_result = Column(Text, nullable=True)
    response_message = Column(Text, nullable=True)
    generator_type = Column(String(225), nullable=True)
    link_count = Column(Integer, nullable=True)
    genai_model_id = Column(Integer, nullable=True)
    genai_model_name = Column(Text, nullable=True)
    genai_model_display_name = Column(Text, nullable=True)
    retriever_id = Column(Integer, nullable=True)
    retriever_name = Column(Text, nullable=True)
    retriever_deploy_name = Column(Text, nullable=True)
    deployment_name = Column(String(225), nullable=True)
    search_scope = Column(Text, nullable=True)
    chat_filter = Column(String(225), nullable=True)
    human_message_id = Column(String(225), ForeignKey("genai_chat_message.message_id"), nullable=True)
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    # 관계
    chat = relationship("GenaiChat", back_populates="messages")
    human_message = relationship(
        "GenaiChatMessage", remote_side=[message_id], back_populates="replies"
    )
    replies = relationship(
        "GenaiChatMessage", back_populates="human_message", cascade="all, delete-orphan"
    )
    links = relationship("GenaiChatMessageLink", back_populates="chat_message", lazy="selectin" , cascade="all")

    # 인덱스
    __table_args__ = (
        Index("chat_id", "chat_id"),
        Index("human_message_id", "human_message_id", unique=True),
    )


class GenaiChatMessageEventData(LGenieBase):
    """LGenie 채팅 메시지 이벤트 데이터 테이블"""

    __tablename__ = "genai_chat_message_event_data"

    event_data_id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(225), ForeignKey("genai_chat_message.message_id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSON, nullable=False)
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    # 관계
    message = relationship("GenaiChatMessage", backref="event_data_list")

    # 인덱스
    __table_args__ = (
        Index("message_id", "message_id"),
    )


class GenaiChatMessageLink(LGenieBase):

    __tablename__ = "genai_chat_message_link"
    message_link_id = Column(Integer(), primary_key=True, autoincrement=True)

    message_id = Column(String(225), ForeignKey("genai_chat_message.message_id"), nullable=False)
    file_document_id = Column(String(225))
    filename = Column(String(225))
    type = Column(String(225))
    title = Column(String(225))
    extension = Column(String(225))
    description =Column(Text)
    expire_date = Column(String(225))
    user_id = Column(String(225))
    lgss_title = Column(String(225))
    view_url = Column(Text)
    match_yn = Column(Boolean, nullable=True, default=None)
    area = Column(String(225))
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    chat_message = relationship("GenaiChatMessage", back_populates="links")
    link_search_blocks = relationship("LinkSearchBlock", back_populates="message_link", cascade="all")

class LinkSearchBlock(LGenieBase):
    __tablename__ = "genai_chat_message_link_block"
    link_block_id = Column(Integer(), primary_key=True, autoincrement=True)

    selector = Column(Boolean)
    block = Column(Text)
    score = Column(Float())
    creation_user_id = Column(String(40), nullable=False)
    creation_date = Column(DateTime, nullable=False)
    last_update_user_id = Column(String(40), nullable=True)
    last_update_date = Column(DateTime, nullable=True)

    message_link_id = Column(Integer(), ForeignKey("genai_chat_message_link.message_link_id"), nullable=False)
    message_link = relationship("GenaiChatMessageLink", back_populates="link_search_blocks")
