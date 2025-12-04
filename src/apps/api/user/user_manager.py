"""
User Manager

사용자 데이터 관리 및 인사정보 메모리 업데이트를 담당하는 모듈
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from logging import getLogger
from queue import Queue
from threading import Lock
from typing import Any, Dict, Optional

from src.database.services import database_service
from src.memory.memory_manager import initialize_memory_manager, memory_manager

logger = getLogger("user_manager")

# 상수 정의
DEFAULT_THREAD_POOL_WORKERS = 2
DEFAULT_MAX_QUEUE_SIZE = 100  # 최대 큐 크기 제한
DEFAULT_IMPORTANCE = 1.0
DEFAULT_AGENT_ID = 1
CAIA_AGENT_CODE = "caia"
PERSONAL_CATEGORY = "PERSONAL"
MEMORY_TYPE_SEMANTIC = "semantic"
SOURCE_FACT = "FACT"


class UserManager:
    """사용자 데이터 관리자"""

    def __init__(self):
        self.logger = logger
        # 큐 크기 제한이 있는 ThreadPoolExecutor 사용
        # max_workers는 동시 실행 스레드 수, 큐 크기는 내부적으로 제한됨
        self._executor = ThreadPoolExecutor(
            max_workers=DEFAULT_THREAD_POOL_WORKERS, 
            thread_name_prefix="memory_save"
        )
        self._pending_tasks = 0
        self._max_queue_size = DEFAULT_MAX_QUEUE_SIZE
        self._task_lock = Lock()

    def save_or_update_user(self, user_data: Dict[str, Any]) -> Optional[int]:
        """사용자 정보를 main 데이터베이스에 저장 또는 업데이트"""
        try:
            if not database_service.is_available():
                self.logger.error("데이터베이스 서비스를 사용할 수 없습니다.")
                return None

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing_user = self._find_existing_user(user_data.get("user_id"))

            if existing_user:
                return self._update_existing_user(
                    existing_user["id"], user_data, current_time
                )
            else:
                return self._create_or_update_user(user_data, current_time)

        except Exception as e:
            self.logger.error(f"사용자 저장/업데이트 실패: {e}")
            return None

    def _find_existing_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """기존 사용자 찾기"""
        return database_service.select_one("users", "id", "user_id = %s", (user_id,))

    def _create_or_update_user(
        self, user_data: Dict[str, Any], current_time: str
    ) -> Optional[int]:
        """새 사용자 생성 또는 업데이트"""
        user_id = self._create_new_user(user_data, current_time)
        if user_id:
            return user_id

        # 중복 키 오류 발생 시 기존 사용자 업데이트 시도
        self.logger.warning(
            f"새 사용자 생성 실패, 기존 사용자 업데이트 시도: {user_data.get('user_id')}"
        )
        existing_user = self._find_existing_user(user_data.get("user_id"))

        if existing_user:
            return self._update_existing_user(
                existing_user["id"], user_data, current_time
            )
        return None

    def _update_existing_user(
        self, user_id: int, user_data: Dict[str, Any], current_time: str
    ) -> Optional[int]:
        """기존 사용자 정보 업데이트"""
        update_data = self._build_user_update_data(user_data, current_time)
        try:
            success = database_service.update("users", update_data, "id = %s", (user_id,))

            if success:
                return user_id
            else:
                self.logger.error(
                    f"사용자 정보 업데이트 실패: user_id={user_data.get('user_id')}, "
                    f"db_id={user_id}, 업데이트된 행이 없습니다."
                )
                return None
        except Exception as e:
            self.logger.error(
                f"사용자 정보 업데이트 중 예외 발생: user_id={user_data.get('user_id')}, "
                f"db_id={user_id}, error={e}"
            )
            return None

    def _build_user_update_data(
        self, user_data: Dict[str, Any], current_time: str
    ) -> Dict[str, Any]:
        """사용자 업데이트 데이터 구성"""
        return {
            "last_update_user_id": user_data.get("user_id", "system"),
            "last_update_date": current_time,
            "username": user_data.get("username", ""),
            "username_eng": user_data.get("username_eng", ""),
            "email": user_data.get("email", ""),
            "nationality": user_data.get("nationality", ""),
            "organ": user_data.get("organ", ""),
            "organ_name": user_data.get("organ_name", ""),
            "location": user_data.get("location", ""),
            "division1_nm": user_data.get("division1_nm", ""),
            "division2_nm": user_data.get("division2_nm", ""),
            "sabun": user_data.get("sabun", ""),
            "name": user_data.get("name", ""),
            "jikwi": user_data.get("jikwi", ""),
            "employee_category": user_data.get("employee_category", ""),
            "job_name": user_data.get("job_name", ""),
            "jikchek_name": user_data.get("jikchek_name", ""),
            "jikwi_name": user_data.get("jikwi_name", ""),
        }

    def _create_new_user(
        self, user_data: Dict[str, Any], current_time: str
    ) -> Optional[int]:
        """새 사용자 생성"""
        insert_data = self._build_user_insert_data(user_data, current_time)
        user_id = database_service.insert("users", insert_data)

        if user_id:
            return user_id
        else:
            self.logger.error(f"새 사용자 생성 실패: {user_data.get('user_id')}")
            return None

    def _build_user_insert_data(
        self, user_data: Dict[str, Any], current_time: str
    ) -> Dict[str, Any]:
        """사용자 삽입 데이터 구성"""
        base_data = self._build_user_update_data(user_data, current_time)
        return {
            "creation_user_id": user_data.get("user_id", "system"),
            "creation_date": current_time,
            "user_id": user_data.get("user_id", ""),
            **base_data,
        }

    def update_personnel_memory(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """사용자의 인사정보를 semantic 메모리에 저장"""
        # user_id가 유효하지 않으면 메모리 저장을 시도하지 않음
        if not user_id or user_id <= 0:
            self.logger.warning(
                f"유효하지 않은 user_id로 메모리 저장을 시도하지 않습니다: user_id={user_id}"
            )
            return False
        
        try:
            if not self._ensure_memory_manager_initialized():
                return False

            agent_id = self._get_caia_agent_id()
            if not agent_id:
                return False

            content = self._build_personnel_content(user_data)

            success = memory_manager.save_memory(
                user_id=user_id,
                content=content,
                memory_type=MEMORY_TYPE_SEMANTIC,
                importance=DEFAULT_IMPORTANCE,
                agent_id=agent_id,
                category=PERSONAL_CATEGORY,
                source=SOURCE_FACT,
            )

            self._log_personnel_memory_result(success, user_id)
            return success

        except Exception as e:
            self.logger.error(f"인사정보 메모리 업데이트 실패: {e}")
            return False

    def _ensure_memory_manager_initialized(self) -> bool:
        """메모리 매니저 초기화 보장"""
        if memory_manager.provider:
            return True

        self.logger.warning("메모리 프로바이더가 초기화되지 않음, 강제 초기화 시도")
        try:
            initialize_memory_manager()
            if memory_manager.provider:
                return True
            else:
                self.logger.error("메모리 프로바이더 강제 초기화 실패")
                return False
        except Exception as e:
            self.logger.error(f"메모리 프로바이더 초기화 중 오류: {e}")
            return False

    def _get_caia_agent_id(self) -> Optional[int]:
        """CAIA 에이전트 ID 가져오기"""
        agent_id = memory_manager.get_agent_id_by_code(CAIA_AGENT_CODE)
        if not agent_id:
            self.logger.error("CAIA 에이전트 ID를 찾을 수 없습니다.")
        return agent_id

    def _log_personnel_memory_result(self, success: bool, user_id: int) -> None:
        """인사정보 메모리 결과 로깅"""
        if not success:
            self.logger.error(f"인사정보 메모리 저장 실패: 사용자 ID {user_id}")

    def _build_personnel_content(self, user_data: Dict[str, Any]) -> str:
        """인사정보 내용 구성"""
        personnel_fields = [
            ("이름", "name"),
            ("사번", "sabun"),
            ("직위", "jikwi"),
            ("직책", "jikchek_name"),
            ("직급명", "jikwi_name"),
            ("직무명", "job_name"),
            ("직원구분", "employee_category"),
            ("조직", "organ_name"),
            ("부문", "division1_nm"),
            ("부서", "division2_nm"),
            ("위치", "location"),
            ("국적", "nationality"),
            ("이메일", "email"),
            ("영문명", "username_eng"),
        ]

        personnel_info = []
        for label, field in personnel_fields:
            value = user_data.get(field, "")
            if value:  # 빈 값이 아닌 경우만 추가
                personnel_info.append(f"{label}: {value}")

        return "\n".join(personnel_info)

    def update_personnel_memory_async(
        self, user_id: int, user_data: Dict[str, Any]
    ) -> None:
        """사용자의 인사정보를 semantic 메모리에 비동기로 저장"""
        # user_id가 유효하지 않으면 메모리 저장을 시도하지 않음
        if not user_id or user_id <= 0:
            self.logger.warning(
                f"유효하지 않은 user_id로 메모리 저장을 시도하지 않습니다: user_id={user_id}"
            )
            return
        
        # 큐 크기 체크 - 메모리 누수 방지
        with self._task_lock:
            if self._pending_tasks >= self._max_queue_size:
                self.logger.warning(
                    f"메모리 저장 큐가 가득 참 ({self._pending_tasks}/{self._max_queue_size}). "
                    f"요청을 건너뜁니다: user_id={user_id}"
                )
                return
            self._pending_tasks += 1
        
        try:
            future = self._executor.submit(
                self._save_personnel_memory_sync, user_id, user_data
            )
            future.add_done_callback(
                lambda f: self._handle_memory_save_result_with_cleanup(f, user_id)
            )
        except Exception as e:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)
            self.logger.error(f"인사정보 메모리 비동기 저장 시작 실패: {e}")

    def _save_personnel_memory_sync(
        self, user_id: int, user_data: Dict[str, Any]
    ) -> bool:
        """동기적으로 인사정보 메모리 저장 (스레드풀에서 실행)"""
        # user_id가 유효하지 않으면 메모리 저장을 시도하지 않음
        if not user_id or user_id <= 0:
            self.logger.warning(
                f"유효하지 않은 user_id로 메모리 저장을 시도하지 않습니다: user_id={user_id}"
            )
            return False
        
        try:
            if not self._ensure_memory_manager_initialized():
                return False

            agent_id = self._get_caia_agent_id()
            if not agent_id:
                return False

            content = self._build_personnel_content(user_data)

            # asyncio.run 대신 _run_async_memory_operation 사용하여 이벤트 루프 관리 개선
            success = self._run_async_memory_operation(
                memory_manager.save_memory(
                    user_id=user_id,
                    content=content,
                    memory_type=MEMORY_TYPE_SEMANTIC,
                    importance=DEFAULT_IMPORTANCE,
                    agent_id=agent_id,
                    category=PERSONAL_CATEGORY,
                    source=SOURCE_FACT,
                )
            )

            return success

        except Exception as e:
            self.logger.error(f"인사정보 메모리 저장 중 오류: {e}")
            return False

    def _handle_memory_save_result(self, future, user_id: int) -> None:
        """메모리 저장 결과 처리"""
        try:
            success = future.result()
            if not success:
                self.logger.error(
                    f"인사정보 메모리 비동기 저장 실패: 사용자 ID {user_id}"
                )
        except Exception as e:
            self.logger.error(f"인사정보 메모리 비동기 저장 결과 처리 중 오류: {e}")
    
    def _handle_memory_save_result_with_cleanup(self, future, user_id: int) -> None:
        """메모리 저장 결과 처리 및 큐 카운터 정리"""
        try:
            self._handle_memory_save_result(future, user_id)
        finally:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)

    def save_memory_async(
        self,
        user_id: int,
        content: str,
        memory_type: str,
        importance: float,
        agent_id: int,
        category: str,
        source: str,
    ) -> None:
        """일반적인 메모리를 비동기로 저장"""
        # 큐 크기 체크 - 메모리 누수 방지
        with self._task_lock:
            if self._pending_tasks >= self._max_queue_size:
                self.logger.warning(
                    f"메모리 저장 큐가 가득 참 ({self._pending_tasks}/{self._max_queue_size}). "
                    f"요청을 건너뜁니다: user_id={user_id}, category={category}"
                )
                return
            self._pending_tasks += 1
        
        try:
            future = self._executor.submit(
                self._save_memory_sync,
                user_id,
                content,
                memory_type,
                importance,
                agent_id,
                category,
                source,
            )
            future.add_done_callback(
                lambda f: self._handle_general_memory_save_result_with_cleanup(f, user_id, category)
            )
        except Exception as e:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)
            self.logger.error(f"메모리 비동기 저장 시작 실패: {e}")

    def update_memory_async(
        self,
        user_id: int,
        content: str,
        memory_type: str,
        importance: float,
        agent_id: int,
        category: str,
        source: str,
    ) -> None:
        """기존 메모리를 삭제하고 새로운 메모리로 교체 (비동기)"""
        # 큐 크기 체크 - 메모리 누수 방지
        with self._task_lock:
            if self._pending_tasks >= self._max_queue_size:
                self.logger.warning(
                    f"메모리 저장 큐가 가득 참 ({self._pending_tasks}/{self._max_queue_size}). "
                    f"요청을 건너뜁니다: user_id={user_id}, category={category}"
                )
                return
            self._pending_tasks += 1
        
        try:
            future = self._executor.submit(
                self._update_memory_sync,
                user_id,
                content,
                memory_type,
                importance,
                agent_id,
                category,
                source,
            )
            future.add_done_callback(
                lambda f: self._handle_memory_update_result_with_cleanup(f, user_id, category)
            )
        except Exception as e:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)
            self.logger.error(f"메모리 비동기 업데이트 시작 실패: {e}")

    def _save_memory_sync(
        self,
        user_id: int,
        content: str,
        memory_type: str,
        importance: float,
        agent_id: int,
        category: str,
        source: str,
    ) -> bool:
        """동기적으로 메모리 저장 (스레드풀에서 실행)"""
        try:
            if not self._ensure_memory_manager_initialized():
                return False

            success = self._run_async_memory_operation(
                memory_manager.save_memory(
                    user_id=user_id,
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    agent_id=agent_id,
                    category=category,
                    source=source,
                )
            )

            self._log_memory_operation_result(
                success, "저장", user_id, memory_type, category
            )
            return success

        except Exception as e:
            self.logger.error(f"메모리 저장 중 오류: {e}")
            return False

    def _run_async_memory_operation(self, coro) -> bool:
        """비동기 메모리 작업을 동기적으로 실행"""
        loop = None
        try:
            # 기존 이벤트 루프가 있는지 확인
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = None
            except RuntimeError:
                loop = None
            
            # 이벤트 루프가 없거나 닫혀있으면 새로 생성
            if loop is None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            return loop.run_until_complete(coro)
        except Exception as e:
            self.logger.error(f"메모리 작업 async 실행 중 오류: {e}")
            return False
        finally:
            # 새로 생성한 루프만 닫기 (기존 루프는 닫지 않음)
            if loop is not None:
                try:
                    # 새로 생성한 루프인지 확인 (is_closed()로 확인 불가하므로 다른 방법 사용)
                    # get_event_loop()로 가져온 루프는 닫지 않음
                    current_loop = None
                    try:
                        current_loop = asyncio.get_event_loop()
                    except RuntimeError:
                        pass
                    
                    # 현재 루프와 다르면 새로 생성한 것이므로 닫기
                    if current_loop is not loop:
                        if not loop.is_closed():
                            loop.close()
                except Exception as cleanup_error:
                    self.logger.warning(f"이벤트 루프 정리 중 오류 (무시): {cleanup_error}")

    def _log_memory_operation_result(
        self,
        success: bool,
        operation: str,
        user_id: int,
        memory_type: str,
        category: str,
    ) -> None:
        """메모리 작업 결과 로깅"""
        if not success:
            self.logger.warning(
                f"메모리 {operation} 실패: user_id={user_id}, type={memory_type}, category={category}"
            )

    def _handle_general_memory_save_result(
        self, future, user_id: int, category: str
    ) -> None:
        """일반 메모리 저장 결과 처리"""
        try:
            success = future.result()
            if not success:
                self.logger.error(
                    f"메모리 비동기 저장 실패: user_id={user_id}, category={category}"
                )
        except Exception as e:
            self.logger.error(f"메모리 비동기 저장 결과 처리 중 오류: {e}")
    
    def _handle_general_memory_save_result_with_cleanup(
        self, future, user_id: int, category: str
    ) -> None:
        """일반 메모리 저장 결과 처리 및 큐 카운터 정리"""
        try:
            self._handle_general_memory_save_result(future, user_id, category)
        finally:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)

    def _update_memory_sync(
        self,
        user_id: int,
        content: str,
        memory_type: str,
        importance: float,
        agent_id: int,
        category: str,
        source: str,
    ) -> bool:
        """동기적으로 메모리 업데이트 (기존 메모리 삭제 후 새로운 메모리로 교체)"""
        try:
            if not self._ensure_memory_manager_initialized():
                return False

            success = self._run_memory_update_operation(
                user_id, content, memory_type, importance, agent_id, category, source
            )

            self._log_memory_operation_result(
                success, "업데이트", user_id, memory_type, category
            )
            return success

        except Exception as e:
            self.logger.error(f"메모리 업데이트 중 오류: {e}")
            return False

    def _run_memory_update_operation(
        self,
        user_id: int,
        content: str,
        memory_type: str,
        importance: float,
        agent_id: int,
        category: str,
        source: str,
    ) -> bool:
        """메모리 업데이트 작업 실행"""
        loop = None
        try:
            # 기존 이벤트 루프가 있는지 확인
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = None
            except RuntimeError:
                loop = None
            
            # 이벤트 루프가 없거나 닫혀있으면 새로 생성
            if loop is None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 1. 기존 메모리 삭제 (동기 메서드)
            memory_manager.delete_memories_by_category(
                user_id=user_id,
                agent_id=agent_id,
                category=category,
                memory_type=memory_type,
            )

            # 2. 새로운 메모리 저장 (비동기 메서드)
            loop.run_until_complete(
                memory_manager.save_memory(
                    user_id=user_id,
                    agent_id=agent_id,
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    category=category,
                    source=source,
                )
            )

            return True
        except Exception as e:
            self.logger.error(f"메모리 업데이트 async 실행 중 오류: {e}")
            return False
        finally:
            # 새로 생성한 루프만 닫기
            if loop is not None:
                try:
                    current_loop = None
                    try:
                        current_loop = asyncio.get_event_loop()
                    except RuntimeError:
                        pass
                    
                    if current_loop is not loop:
                        if not loop.is_closed():
                            loop.close()
                except Exception as cleanup_error:
                    self.logger.warning(f"이벤트 루프 정리 중 오류 (무시): {cleanup_error}")

    def _handle_memory_update_result(self, future, user_id: int, category: str) -> None:
        """메모리 업데이트 결과 처리"""
        try:
            success = future.result()
            if not success:
                self.logger.error(
                    f"메모리 비동기 업데이트 실패: user_id={user_id}, category={category}"
                )
        except Exception as e:
            self.logger.error(f"메모리 비동기 업데이트 결과 처리 중 오류: {e}")
    
    def _handle_memory_update_result_with_cleanup(
        self, future, user_id: int, category: str
    ) -> None:
        """메모리 업데이트 결과 처리 및 큐 카운터 정리"""
        try:
            self._handle_memory_update_result(future, user_id, category)
        finally:
            with self._task_lock:
                self._pending_tasks = max(0, self._pending_tasks - 1)

    def close(self):
        """리소스 정리"""
        try:
            if hasattr(self, "_executor"):
                self._executor.shutdown(wait=True)
        except Exception as e:
            self.logger.error(f"UserManager 리소스 정리 중 오류: {e}")


# 전역 인스턴스
user_manager = UserManager()
