"""
SQLAlchemy 데이터베이스 연결 관리

FastAPI와 SQLAlchemy를 사용한 데이터베이스 연결 및 세션 관리
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from configs.app_config import load_config

from ..models import Base

logger = None


def get_logger():
    """로거 가져오기 (지연 로딩)"""
    global logger
    if logger is None:
        from logging import getLogger

        logger = getLogger("database")
    return logger


def get_database_url(database_name: str = "main") -> str:
    """데이터베이스 URL 구성"""
    # MAIN과 LGENIE의 URL 결정 로직을 분리
    if database_name == "main":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            # 개별 환경변수/설정으로 구성
            config = load_config()
            database_config = config.get("database", {})
            target_database_config = database_config.get("main", {})
            host = target_database_config.get("host", "localhost")
            port = int(target_database_config.get("port", "3306"))
            user = target_database_config.get("user", "user")
            password = target_database_config.get("password", "password")
            database = target_database_config.get("database", "expert_agents")
            database_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
        else:
            if database_url.startswith("mysql://"):
                database_url = database_url.replace("mysql://", "mysql+pymysql://")
        return database_url

    # LGenie는 항상 별도의 URL을 우선 사용한다
    if database_name == "lgenie":
        lgenie_url = os.getenv("LGENIE_DATABASE_URL")
        if lgenie_url:
            if lgenie_url.startswith("mysql://"):
                lgenie_url = lgenie_url.replace("mysql://", "mysql+pymysql://")
            return lgenie_url

        # LGenie 전용 환경변수/설정으로 구성
        config = load_config()
        database_config = config.get("database", {})
        target_database_config = database_config.get("lgenie", {})
        host = os.getenv("LGENIE_DATABASE_HOST", target_database_config.get("host", "localhost"))
        port = int(os.getenv("LGENIE_DATABASE_PORT", target_database_config.get("port", "3306")))
        user = os.getenv("LGENIE_DATABASE_USER", target_database_config.get("user", "user"))
        password = os.getenv("LGENIE_DATABASE_PW", target_database_config.get("password", "password"))
        database = target_database_config.get("database", "myexa")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

    # 기타 이름은 main과 동일 로직
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        config = load_config()
        database_config = config.get("database", {})
        target_database_config = database_config.get(database_name, {})
        host = target_database_config.get("host", "localhost")
        port = int(target_database_config.get("port", "3306"))
        user = target_database_config.get("user", "user")
        password = target_database_config.get("password", "password")
        database = target_database_config.get("database", "expert_agents")
        database_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"
    else:
        if database_url.startswith("mysql://"):
            database_url = database_url.replace("mysql://", "mysql+pymysql://")

    return database_url


def create_database_engine(database_name: str = "main", log_initialization: bool = False) -> Engine:
    """데이터베이스 엔진 생성"""
    database_url = get_database_url(database_name)
    config = load_config()
    
    # 연결 풀 설정 (설정 파일에서 읽기)
    database_config = config.get("database", {})
    target_db_config = database_config.get(database_name, database_config.get("main", {}))
    
    # pool_size: 설정 파일 > 기본값(32)
    pool_size = int(target_db_config.get("pool_size", 32))
    
    # max_overflow: 설정 파일 > 기본값(pool_size의 2배)
    max_overflow = int(target_db_config.get("max_overflow", pool_size * 2))
    
    # pool_timeout: 설정 파일 > 기본값(10초)
    pool_timeout = int(target_db_config.get("pool_timeout", 10))
    
    # 엔진 설정 (pymysql 명시적 사용)
    engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=config.get("logging", {}).get("sql_echo", "false").lower() == "true",
        connect_args={
            "charset": "utf8mb4",
            "autocommit": False,
        },
        # pymysql 드라이버 명시적 지정
        module=None,  # 기본 모듈 사용
    )
    
    # 연결 풀 설정 로깅 (명시적으로 요청된 경우에만)
    if log_initialization:
        logger = get_logger()
    return engine


# 전역 엔진 및 세션 팩토리
_engine: Engine = None
_SessionLocal: sessionmaker = None
_lgenie_engine: Engine = None
_lgenie_SessionLocal: sessionmaker = None


def get_engine() -> Engine:
    """데이터베이스 엔진 가져오기"""
    global _engine
    _engine = create_database_engine("main", log_initialization=False)
    return _engine


def get_session_local() -> sessionmaker:
    """세션 팩토리 가져오기"""
    global _SessionLocal
    engine = get_engine()
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal


def get_lgenie_engine() -> Engine:
    """LGenie 데이터베이스 엔진 가져오기"""
    global _lgenie_engine
    if _lgenie_engine is None:
        logger = get_logger()
        # 연결 풀 설정을 먼저 로깅
        config = load_config()
        database_config = config.get("database", {})
        target_db_config = database_config.get("lgenie", {})
        pool_size = int(target_db_config.get("pool_size", 32))
        max_overflow = int(target_db_config.get("max_overflow", pool_size * 2))
        pool_timeout = int(target_db_config.get("pool_timeout", 10))
        
        logger.info(
            f"[DB_POOL] lgenie 데이터베이스 연결 풀 초기화: "
            f"pool_size={pool_size}, max_overflow={max_overflow}, "
            f"max_connections={pool_size + max_overflow}, pool_timeout={pool_timeout}초"
        )
        
        _lgenie_engine = create_database_engine("lgenie", log_initialization=False)
        logger.info("LGenie 데이터베이스 엔진이 초기화되었습니다.")
    return _lgenie_engine


def get_lgenie_session_local() -> sessionmaker:
    """LGenie 세션 팩토리 가져오기"""
    global _lgenie_SessionLocal
    if _lgenie_SessionLocal is None:
        engine = get_lgenie_engine()
        _lgenie_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _lgenie_SessionLocal



def get_db() -> Generator[Session, None, None]:
    """데이터베이스 세션 의존성 (FastAPI용)"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def get_async_db() -> AsyncGenerator[Session, None]:
    """비동기 데이터베이스 세션 컨텍스트 매니저"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_lgenie_db() -> Generator[Session, None, None]:
    """LGenie 데이터베이스 세션 의존성 (FastAPI용)"""
    SessionLocal = get_lgenie_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def get_lgenie_async_db() -> AsyncGenerator[Session, None]:
    """LGenie 비동기 데이터베이스 세션 컨텍스트 매니저"""
    SessionLocal = get_lgenie_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """테이블 생성"""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    get_logger().info("데이터베이스 테이블이 생성되었습니다.")


def drop_tables():
    """테이블 삭제"""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    get_logger().info("데이터베이스 테이블이 삭제되었습니다.")


def check_connection() -> bool:
    """데이터베이스 연결 확인"""
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        get_logger().info("데이터베이스 연결이 정상입니다.")
        return True
    except Exception as e:
        get_logger().error(f"데이터베이스 연결 실패: {e}")
        return False


def close_connections():
    """데이터베이스 연결 종료"""
    global _engine, _SessionLocal, _lgenie_engine, _lgenie_SessionLocal
    try:
        # 메인 데이터베이스 연결 종료
        if _SessionLocal:
            _SessionLocal.close_all()
            _SessionLocal = None
            get_logger().info("데이터베이스 세션 팩토리가 종료되었습니다.")

        if _engine:
            _engine.dispose()
            _engine = None
            get_logger().info("데이터베이스 엔진이 종료되었습니다.")

        # LGenie 데이터베이스 연결 종료
        if _lgenie_SessionLocal:
            _lgenie_SessionLocal.close_all()
            _lgenie_SessionLocal = None
            get_logger().info("LGenie 데이터베이스 세션 팩토리가 종료되었습니다.")

        if _lgenie_engine:
            _lgenie_engine.dispose()
            _lgenie_engine = None
            get_logger().info("LGenie 데이터베이스 엔진이 종료되었습니다.")
    except Exception as e:
        get_logger().error(f"데이터베이스 연결 종료 중 오류: {e}")
