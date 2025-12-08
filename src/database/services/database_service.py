"""
Database Service

공통 데이터베이스 서비스 - SQLAlchemy ORM 기반으로 리팩토링
기존 인터페이스는 유지하면서 내부적으로 ORM을 사용
"""

from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from src.database.connection import get_db, get_lgenie_db

logger = getLogger("database")


class DatabaseService:
    """공통 데이터베이스 서비스 (ORM 기반)

    의존성 주입 패턴을 지원하며, 세션이 제공되지 않으면 자동으로 생성합니다.
    FastAPI 의존성 주입과 호환되도록 설계되었습니다.

    사용 예시:
        # 의존성 주입 사용 (권장)
        def my_endpoint(db: Session = Depends(get_db)):
            service = DatabaseService(db_session=db)
            # ...

        # 자동 세션 생성 (하위 호환성)
        service = DatabaseService()
        # ...
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Args:
            db_session: 주입할 데이터베이스 세션 (선택적)
                       제공되지 않으면 실제 사용 시점에 자동으로 생성합니다.
        """
        self._db_session = db_session
        if self._db_session is not None:
            logger.debug("데이터베이스 서비스가 주입된 세션으로 초기화되었습니다.")
        # 지연 초기화: 모듈 임포트 시점에 DB 연결을 시도하지 않음
        # 실제 사용 시점에 _get_session()에서 세션을 생성함

    def _init_session(self):
        """데이터베이스 세션 초기화 (하위 호환성)"""
        # 하위 호환성을 위해 유지하지만 실제로는 _get_session()이 세션을 생성함
        if not self._db_session:
            self._get_session()

    def _get_session(self) -> Optional[Session]:
        """데이터베이스 세션 가져오기 (지연 초기화)"""
        if not self._db_session:
            try:
                self._db_session = next(get_db())
                logger.debug(
                    "데이터베이스 서비스가 자동 생성된 세션으로 초기화되었습니다."
                )
            except Exception as e:
                logger.error(f"데이터베이스 세션 생성 실패: {e}")
                return None
        return self._db_session

    def get_connection(self):
        """데이터베이스 연결 가져오기 (ORM 세션 반환)"""
        return self._get_session()

    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetch: bool = False,
        fetch_one: bool = False,
        commit: bool = True,
    ) -> Optional[Any]:
        """
        쿼리 실행 (ORM 기반)

        Args:
            query: 실행할 SQL 쿼리
            params: 쿼리 파라미터
            fetch: 결과를 가져올지 여부
            fetch_one: 하나의 결과만 가져올지 여부
            commit: 트랜잭션 커밋 여부

        Returns:
            쿼리 결과 또는 None
        """
        db = self._get_session()
        if not db:
            return None

        try:
            from sqlalchemy import text

            result = db.execute(text(query), params or {})

            if fetch:
                if fetch_one:
                    return result.fetchone()
                else:
                    return result.fetchall()
            else:
                if commit:
                    db.commit()
                return result.rowcount > 0 if result.rowcount is not None else True

        except Exception as e:
            logger.error(f"쿼리 실행 실패: {e}")
            if commit:
                db.rollback()
            return None

    def insert(self, table: str, data: Dict[str, Any]) -> Optional[int]:
        """
        데이터 삽입 (ORM 기반)

        Args:
            table: 테이블명
            data: 삽입할 데이터

        Returns:
            삽입된 레코드의 ID 또는 None
        """
        if not data:
            return None

        db = self._get_session()
        if not db:
            return None

        try:
            from sqlalchemy import text

            columns = list(data.keys())
            placeholders = [f":{col}" for col in columns]

            query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
            result = db.execute(text(query), data)
            db.commit()

            return result.lastrowid
        except Exception as e:
            logger.error(f"데이터 삽입 실패: {e}")
            db.rollback()
            return None

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where_clause: str,
        where_params: Optional[Tuple] = None,
    ) -> bool:
        """
        데이터 업데이트 (ORM 기반)

        Args:
            table: 테이블명
            data: 업데이트할 데이터
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터

        Returns:
            성공 여부
        """
        if not data:
            return False

        db = self._get_session()
        if not db:
            return False

        try:
            from sqlalchemy import text

            set_clause = ", ".join([f"{col} = :{col}" for col in data.keys()])
            query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"

            params = data.copy()
            if where_params:
                # where_params 타입 검증 및 정규화
                if isinstance(where_params, str):
                    where_params = (where_params,)

                # WHERE 절 파라미터를 딕셔너리에 추가
                for i, param in enumerate(where_params):
                    params[f"param_{i}"] = param
                # WHERE 절의 %s를 :param_0, :param_1 등으로 변경
                where_clause_updated = where_clause
                for i in range(len(where_params)):
                    where_clause_updated = where_clause_updated.replace(
                        "%s", f":param_{i}", 1
                    )
                query = f"UPDATE {table} SET {set_clause} WHERE {where_clause_updated}"

            result = db.execute(text(query), params)
            db.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"데이터 업데이트 실패: {e}")
            db.rollback()
            return False

    def select(
        self,
        table: str,
        columns: str = "*",
        where_clause: Optional[str] = None,
        where_params: Optional[Tuple] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        데이터 조회 (ORM 기반)

        Args:
            table: 테이블명
            columns: 조회할 컬럼들
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터
            order_by: ORDER BY 절
            limit: LIMIT 절

        Returns:
            조회된 데이터 리스트
        """
        db = self._get_session()
        if not db:
            return []

        try:
            from sqlalchemy import text

            query = f"SELECT {columns} FROM {table}"
            params = {}

            if where_clause:
                query += f" WHERE {where_clause}"
                if where_params:
                    # 문자열인 경우 튜플로 변환
                    if isinstance(where_params, str):
                        where_params = (where_params,)

                    for i, param in enumerate(where_params):
                        params[f"param_{i}"] = param
                    # WHERE 절의 %s를 :param_0, :param_1 등으로 변경
                    for i in range(len(where_params)):
                        where_clause = where_clause.replace("%s", f":param_{i}", 1)
                    query = f"SELECT {columns} FROM {table} WHERE {where_clause}"

            # Order by clause 추가
            if order_by:
                query += f" ORDER BY {order_by}"

            if limit:
                query += f" LIMIT {limit}"

            result = db.execute(text(query), params)
            rows = result.fetchall()

            # Row 객체를 딕셔너리로 변환
            if rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            return []
        except Exception as e:
            logger.error(f"데이터 조회 실패: {e}")
            return []

    def select_one(
        self,
        table: str,
        columns: str = "*",
        where_clause: Optional[str] = None,
        where_params: Optional[Tuple] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        단일 데이터 조회 (ORM 기반)

        Args:
            table: 테이블명
            columns: 조회할 컬럼들
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터

        Returns:
            조회된 데이터 또는 None
        """
        results = self.select(table, columns, where_clause, where_params, limit=1)
        return results[0] if results else None

    def delete(
        self, table: str, where_clause: str, where_params: Optional[Tuple] = None
    ) -> bool:
        """
        데이터 삭제 (ORM 기반)

        Args:
            table: 테이블명
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터

        Returns:
            성공 여부
        """
        db = self._get_session()
        if not db:
            return False

        try:
            from sqlalchemy import text

            query = f"DELETE FROM {table} WHERE {where_clause}"
            params = {}

            if where_params:
                # where_params 타입 검증 및 정규화
                if isinstance(where_params, str):
                    where_params = (where_params,)
                elif not isinstance(where_params, (tuple, list)):
                    raise TypeError(
                        f"where_params must be a tuple, list, or string, got {type(where_params).__name__}"
                    )

                for i, param in enumerate(where_params):
                    params[f"param_{i}"] = param
                # WHERE 절의 %s를 :param_0, :param_1 등으로 변경
                for i in range(len(where_params)):
                    where_clause = where_clause.replace("%s", f":param_{i}", 1)
                query = f"DELETE FROM {table} WHERE {where_clause}"

            result = db.execute(text(query), params)
            db.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"데이터 삭제 실패: {e}")
            db.rollback()
            return False

    def close(self):
        """데이터베이스 연결 종료"""
        if self._db_session:
            try:
                self._db_session.close()
                logger.info("데이터베이스 서비스가 종료되었습니다.")
            except Exception as e:
                logger.error(f"데이터베이스 서비스 종료 실패: {e}")
            finally:
                self._db_session = None

    def is_available(self) -> bool:
        """데이터베이스 서비스 사용 가능 여부"""
        # 세션이 없으면 시도해서 생성해봄
        session = self._get_session()
        return session is not None


class LGenieDatabaseService:
    """LGenie 데이터베이스 전용 서비스 (ORM 기반)

    의존성 주입 패턴을 지원하며, 세션이 제공되지 않으면 자동으로 생성합니다.

    사용 예시:
        # 의존성 주입 사용 (권장)
        def my_endpoint(db: Session = Depends(get_lgenie_db)):
            service = LGenieDatabaseService(db_session=db)
            # ...

        # 자동 세션 생성 (하위 호환성)
        service = LGenieDatabaseService()
        # ...
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Args:
            db_session: 주입할 LGenie 데이터베이스 세션 (선택적)
                       제공되지 않으면 실제 사용 시점에 자동으로 생성합니다.
        """
        self._db_session = db_session
        if self._db_session is not None:
            logger.debug(
                "LGenie 데이터베이스 서비스가 주입된 세션으로 초기화되었습니다."
            )

    def _init_session(self):
        """LGenie 데이터베이스 세션 초기화 (하위 호환성)"""
        if not self._db_session:
            self._get_session()

    def _get_session(self) -> Optional[Session]:
        """LGenie 데이터베이스 세션 가져오기 (지연 초기화)"""
        if not self._db_session:
            try:
                self._db_session = next(get_lgenie_db())
                logger.debug(
                    "LGenie 데이터베이스 서비스가 자동 생성된 세션으로 초기화되었습니다."
                )
            except Exception as e:
                logger.error(f"LGenie 데이터베이스 세션 생성 실패: {e}")
                return None
        return self._db_session

    def get_connection(self):
        """LGenie 데이터베이스 연결 가져오기 (ORM 세션 반환)"""
        return self._get_session()

    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetch: bool = False,
        fetch_one: bool = False,
        commit: bool = True,
    ) -> Optional[Any]:
        """
        LGenie 쿼리 실행 (ORM 기반)

        Args:
            query: 실행할 SQL 쿼리
            params: 쿼리 파라미터
            fetch: 결과를 가져올지 여부
            fetch_one: 하나의 결과만 가져올지 여부
            commit: 트랜잭션 커밋 여부

        Returns:
            쿼리 결과 또는 None
        """
        db = self._get_session()
        if not db:
            return None

        try:
            from sqlalchemy import text

            result = db.execute(text(query), params or {})

            if fetch:
                if fetch_one:
                    return result.fetchone()
                else:
                    return result.fetchall()
            else:
                if commit:
                    db.commit()
                return result.rowcount > 0 if result.rowcount is not None else True

        except Exception as e:
            logger.error(f"LGenie 쿼리 실행 실패: {e}")
            if commit:
                db.rollback()
            return None

    def insert(self, table: str, data: Dict[str, Any]) -> Optional[int]:
        """
        LGenie 데이터 삽입 (ORM 기반)

        Args:
            table: 테이블명
            data: 삽입할 데이터

        Returns:
            삽입된 레코드의 ID 또는 None
        """
        if not data:
            return None

        db = self._get_session()
        if not db:
            return None

        try:
            from sqlalchemy import text

            columns = list(data.keys())
            placeholders = [f":{col}" for col in columns]

            query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
            result = db.execute(text(query), data)
            db.commit()

            return result.lastrowid
        except Exception as e:
            logger.error(f"LGenie 데이터 삽입 실패: {e}")
            db.rollback()
            return None

    def select(
        self,
        table: str,
        columns: str = "*",
        where_clause: Optional[str] = None,
        where_params: Optional[Tuple] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        LGenie 데이터 조회 (ORM 기반)

        Args:
            table: 테이블명
            columns: 조회할 컬럼들
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터
            order_by: ORDER BY 절
            limit: LIMIT 절

        Returns:
            조회된 데이터 리스트
        """
        db = self._get_session()
        if not db:
            return []

        try:
            from sqlalchemy import text

            query = f"SELECT {columns} FROM {table}"
            params = {}

            if where_clause:
                query += f" WHERE {where_clause}"
                if where_params:
                    # 문자열인 경우 튜플로 변환
                    if isinstance(where_params, str):
                        where_params = (where_params,)

                    for i, param in enumerate(where_params):
                        params[f"param_{i}"] = param
                    # WHERE 절의 %s를 :param_0, :param_1 등으로 변경
                    for i in range(len(where_params)):
                        where_clause = where_clause.replace("%s", f":param_{i}", 1)
                    query = f"SELECT {columns} FROM {table} WHERE {where_clause}"

            # Order by clause 추가
            if order_by:
                query += f" ORDER BY {order_by}"

            if limit:
                query += f" LIMIT {limit}"

            result = db.execute(text(query), params)
            rows = result.fetchall()

            # Row 객체를 딕셔너리로 변환
            if rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in rows]
            return []
        except Exception as e:
            logger.error(f"LGenie 데이터 조회 실패: {e}")
            return []

    def select_one(
        self,
        table: str,
        columns: str = "*",
        where_clause: Optional[str] = None,
        where_params: Optional[Tuple] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        LGenie 단일 데이터 조회 (ORM 기반)

        Args:
            table: 테이블명
            columns: 조회할 컬럼들
            where_clause: WHERE 절
            where_params: WHERE 절 파라미터

        Returns:
            조회된 데이터 또는 None
        """
        results = self.select(table, columns, where_clause, where_params, limit=1)
        return results[0] if results else None

    def close(self):
        """LGenie 데이터베이스 연결 종료"""
        if self._db_session:
            try:
                self._db_session.close()
                logger.info("LGenie 데이터베이스 서비스가 종료되었습니다.")
            except Exception as e:
                logger.error(f"LGenie 데이터베이스 서비스 종료 실패: {e}")
            finally:
                self._db_session = None

    def is_available(self) -> bool:
        """LGenie 데이터베이스 서비스 사용 가능 여부"""
        # 세션이 없으면 시도해서 생성해봄
        session = self._get_session()
        return session is not None


# 전역 인스턴스
database_service = DatabaseService()
lgenie_database_service = LGenieDatabaseService()
