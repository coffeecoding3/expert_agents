"""
Database CLI Module

데이터베이스 관리 CLI 도구를 포함하는 모듈
"""

from .cli import db

# cli를 db의 alias로 export
cli = db

__all__ = [
    "cli",
]
