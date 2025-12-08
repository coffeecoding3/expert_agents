"""
FastAPI 의존성을 위한 데이터베이스 세션 관리

FastAPI에서 SQLAlchemy 세션을 의존성으로 주입하기 위한 유틸리티
"""

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from .connection import get_db


def get_database_session() -> Generator[Session, None, None]:
    """FastAPI 의존성으로 사용할 데이터베이스 세션"""
    yield from get_db()


# FastAPI 의존성 타입 별칭
DatabaseSession = Depends(get_database_session)
