"""
데이터베이스 관리 CLI 명령어

Alembic migration 관리를 위한 CLI 유틸리티
"""

import os
import sys
from typing import Optional

import click
from alembic import command
from alembic.config import Config

from ..connection import get_database_url


def get_alembic_config() -> Config:
    """Alembic 설정 가져오기"""
    # 프로젝트 루트 디렉토리 계산
    # src/database/cli/cli.py -> src/database/cli -> src/database -> src -> 프로젝트 루트
    project_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    )

    # Alembic 설정 파일 경로
    alembic_cfg = os.path.join(project_root, "alembic.ini")

    # 설정 객체 생성 (절대 경로 사용)
    config = Config(alembic_cfg)

    # script_location을 명시적으로 설정 (%(here)s 토큰 문제 해결)
    migrations_path = os.path.join(project_root, "migrations")
    config.set_main_option("script_location", migrations_path)

    # 데이터베이스 URL은 migrations/env.py에서 직접 설정하므로 여기서는 설정하지 않음
    # configparser의 interpolation 문제를 피하기 위해 env.py에서 직접 get_database_url() 사용
    # config.set_main_option("sqlalchemy.url", get_database_url())

    return config


@click.group()
def db():
    """데이터베이스 관리 명령어"""
    pass


@db.command()
@click.option("--message", "-m", required=True, help="Migration 메시지")
def create_migration(message: str):
    """새로운 migration 생성"""
    try:
        config = get_alembic_config()
        command.revision(config, autogenerate=True, message=message)
        click.echo(f"Migration이 생성되었습니다: {message}")
    except Exception as e:
        click.echo(f"Migration 생성 실패: {e}", err=True)
        sys.exit(1)


@db.command()
@click.option("--revision", default="head", help="적용할 revision (기본값: head)")
def upgrade(revision: str):
    """Migration 적용"""
    try:
        config = get_alembic_config()
        command.upgrade(config, revision)
        click.echo(f"Migration이 적용되었습니다: {revision}")
    except Exception as e:
        click.echo(f"Migration 적용 실패: {e}", err=True)
        sys.exit(1)


@db.command()
@click.option("--revision", default="-1", help="되돌릴 revision (기본값: -1)")
def downgrade(revision: str):
    """Migration 되돌리기"""
    try:
        config = get_alembic_config()
        command.downgrade(config, revision)
        click.echo(f"Migration이 되돌려졌습니다: {revision}")
    except Exception as e:
        click.echo(f"Migration 되돌리기 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def current():
    """현재 migration 상태 확인"""
    try:
        config = get_alembic_config()
        command.current(config)
    except Exception as e:
        click.echo(f"Migration 상태 확인 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def history():
    """Migration 히스토리 확인"""
    try:
        config = get_alembic_config()
        command.history(config)
    except Exception as e:
        click.echo(f"Migration 히스토리 확인 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def init():
    """데이터베이스 초기화 (테이블 생성)"""
    try:
        from ..connection import create_tables

        create_tables()
        click.echo("데이터베이스가 초기화되었습니다.")
    except Exception as e:
        click.echo(f"데이터베이스 초기화 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def reset():
    """데이터베이스 리셋 (모든 테이블 삭제 후 재생성)"""
    try:
        from ..connection import create_tables, drop_tables

        drop_tables()
        create_tables()
        click.echo("데이터베이스가 리셋되었습니다.")
    except Exception as e:
        click.echo(f"데이터베이스 리셋 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def check():
    """데이터베이스 연결 확인"""
    try:
        from ..connection import check_connection

        if check_connection():
            click.echo("데이터베이스 연결이 정상입니다.")
        else:
            click.echo("데이터베이스 연결에 실패했습니다.", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"데이터베이스 연결 확인 실패: {e}", err=True)
        sys.exit(1)


@db.command()
@click.option("--database", default=None, help="생성할 데이터베이스 이름 (기본값: 설정 파일의 database 값)")
def create_database(database: Optional[str]):
    """데이터베이스 생성"""
    try:
        from sqlalchemy import create_engine, text
        from ..connection import get_database_url
        from configs.app_config import load_config
        
        # 데이터베이스 이름 결정
        if not database:
            config = load_config()
            database_config = config.get("database", {})
            target_database_config = database_config.get("main", {})
            database = target_database_config.get("database", "expert_agents")
        
        # 데이터베이스 URL에서 데이터베이스 이름 제거하여 서버에 연결
        database_url = get_database_url()
        # URL 형식: mysql+pymysql://user:password@host:port/database?charset=utf8mb4
        # 마지막 / 이후 부분(데이터베이스 이름과 쿼리 파라미터) 제거
        from urllib.parse import urlparse, urlunparse
        
        parsed = urlparse(database_url)
        # path를 빈 문자열로 설정하여 데이터베이스 이름 제거
        base_parsed = parsed._replace(path="")
        base_url = urlunparse(base_parsed)
        
        # 서버에 연결 (데이터베이스 이름 없이)
        engine = create_engine(base_url, pool_pre_ping=True)
        
        with engine.connect() as connection:
            # 데이터베이스가 이미 존재하는지 확인
            result = connection.execute(
                text(f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{database}'")
            )
            if result.fetchone():
                click.echo(f"데이터베이스 '{database}'가 이미 존재합니다.")
            else:
                # 데이터베이스 생성
                connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                connection.commit()
                click.echo(f"데이터베이스 '{database}'가 생성되었습니다.")
        
        engine.dispose()
    except Exception as e:
        click.echo(f"데이터베이스 생성 실패: {e}", err=True)
        sys.exit(1)


@db.command()
@click.option("--revision", required=True, help="설정할 revision ID")
def stamp(revision: str):
    """마이그레이션 버전을 수동으로 설정 (데이터베이스 초기화 시 사용)"""
    try:
        config = get_alembic_config()
        command.stamp(config, revision)
        click.echo(f"마이그레이션 버전이 '{revision}'으로 설정되었습니다.")
    except Exception as e:
        click.echo(f"마이그레이션 버전 설정 실패: {e}", err=True)
        sys.exit(1)


@db.command()
def reset_version():
    """마이그레이션 버전을 init_schema.py의 revision(000000000000)으로 초기화"""
    try:
        from sqlalchemy import create_engine, text
        from ..connection import get_database_url
        
        # 데이터베이스 URL 가져오기
        database_url = get_database_url()
        engine = create_engine(database_url, pool_pre_ping=True)
        
        with engine.connect() as connection:
            # alembic_version 테이블이 있는지 확인
            result = connection.execute(
                text("SHOW TABLES LIKE 'alembic_version'")
            )
            if result.fetchone():
                # 기존 버전 삭제 후 새 버전 삽입
                connection.execute(text("DELETE FROM alembic_version"))
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('000000000000')")
                )
                connection.commit()
                click.echo("마이그레이션 버전이 '000000000000' (init_schema)으로 초기화되었습니다.")
            else:
                # 테이블이 없으면 생성
                connection.execute(
                    text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, PRIMARY KEY (version_num))")
                )
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('000000000000')")
                )
                connection.commit()
                click.echo("alembic_version 테이블을 생성하고 '000000000000' (init_schema)으로 초기화되었습니다.")
        
        engine.dispose()
        click.echo("이제 'db upgrade' 명령어로 마이그레이션을 적용할 수 있습니다.")
    except Exception as e:
        click.echo(f"마이그레이션 버전 초기화 실패: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    db()
