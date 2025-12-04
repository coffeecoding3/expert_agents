"""
REST API Application

관리/운영용 REST API (상태 조회, 승인, 헬스체크)
"""

import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from logging import getLogger
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from configs.app_config import load_config
from src.agents.agent_registry import agent_registry
from src.agents.caia_agent import CAIAAgent
from src.agents.components.common.tool_registry import ToolRegistry
from src.llm.manager import llm_manager
from src.memory.memory_manager import initialize_memory_manager
from src.utils.log_collector import collector

from src.agents.raih_agent import RAIHAgent
from src.agents.lexai_agent import LexAIAgent

# 라우터 임포트
from src.apps.api.routers.auth import agent_auth_router, agents_list_router
from src.apps.api.routers.base_router import base_router
from src.apps.api.routers.chat import agent_router, chat_management_router
from src.apps.api.routers.logs.log_router import log_router
from src.apps.api.routers.memory import memory_router
from src.apps.api.routers.lexai.lexai_router import lexai_router

# 로그 설정 중복 실행 방지 플래그
_logging_configured = False


# ============================================================================
# 유틸리티 함수
# ============================================================================

def get_project_root() -> str:
    """프로젝트 루트 디렉토리 경로 반환"""
    if "PROJECT_ROOT" in os.environ:
        return os.environ["PROJECT_ROOT"]
    # src/apps/api/main.py -> src/apps/api -> src/apps -> src -> 프로젝트 루트
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )


def get_active_agent_code() -> Optional[str]:
    """활성 에이전트 코드 반환 (단일 에이전트 모드)"""
    code = os.getenv("ACTIVE_AGENT_CODE", "").strip().lower()
    return code if code else None


# ============================================================================
# 로깅 설정
# ============================================================================

def setup_logging():
    """로깅 설정 함수 - 중복 실행 방지"""
    global _logging_configured

    if _logging_configured:
        _update_existing_logging_handlers()
        return

    _initialize_logging()
    _logging_configured = True


def _update_existing_logging_handlers():
    """이미 설정된 로깅 핸들러 업데이트"""
    root_logger = logging.getLogger()
    from src.utils.log_rotation_handler import DateAndRowRotatingFileHandler

    enable_console = os.getenv("ENABLE_CONSOLE_LOGGING", "false").lower() == "true"
    max_handlers = 2 if enable_console else 1

    # 콘솔 핸들러가 필요한데 없는 경우 추가
    console_handler_found = False
    if enable_console:
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, DateAndRowRotatingFileHandler
            ):
                from src.apps.api.logging.sse_log_handler import SSELogHandler
                if not isinstance(handler, SSELogHandler):
                    console_handler_found = True
                    break

        if not console_handler_found:
            _add_console_handler(root_logger)

    # 중복 핸들러 제거
    if len(root_logger.handlers) > max_handlers:
        _cleanup_duplicate_handlers(root_logger, enable_console, console_handler_found)


def _initialize_logging():
    """로깅 초기화"""
    _level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    _level = getattr(logging, _level_name, logging.INFO)

    project_root = get_project_root()
    logs_dir = os.path.join(project_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # 파일 핸들러 설정
    from src.utils.log_rotation_handler import DateAndRowRotatingFileHandler

    log_file = os.path.join(project_root, "server.log")
    max_rows = int(os.getenv("LOG_MAX_ROWS", "10000"))

    file_handler = DateAndRowRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=0,
        encoding="utf-8",
        max_rows=max_rows,
        logs_dir=logs_dir,
    )
    file_handler.setLevel(_level)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # 콘솔 핸들러 설정
    enable_console_logging = (
        os.getenv("ENABLE_CONSOLE_LOGGING", "false").lower() == "true"
    )
    console_handler = None
    if enable_console_logging:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_level)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(_level)

    # MCP 관련 로거 레벨 설정
    _configure_mcp_loggers()

    # 기존 핸들러 제거 후 새로 추가
    _clear_existing_handlers(root_logger)
    root_logger.addHandler(file_handler)
    if console_handler:
        root_logger.addHandler(console_handler)


def _add_console_handler(root_logger: logging.Logger):
    """콘솔 핸들러 추가"""
    _level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    _level = getattr(logging, _level_name, logging.INFO)
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_level)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    root_logger.addHandler(console_handler)


def _cleanup_duplicate_handlers(
    root_logger: logging.Logger, enable_console: bool, console_handler_found: bool
):
    """중복 핸들러 제거"""
    from src.utils.log_rotation_handler import DateAndRowRotatingFileHandler
    from src.apps.api.logging.sse_log_handler import SSELogHandler

    file_handler_found = False
    sse_handler_found = False

    for handler in root_logger.handlers[:]:
        if isinstance(handler, DateAndRowRotatingFileHandler) and not file_handler_found:
            file_handler_found = True
        elif isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, DateAndRowRotatingFileHandler
        ):
            if isinstance(handler, SSELogHandler):
                if not sse_handler_found:
                    sse_handler_found = True
                else:
                    _remove_handler(root_logger, handler)
            elif enable_console and console_handler_found:
                pass  # 콘솔 핸들러는 유지
            else:
                _remove_handler(root_logger, handler)
        else:
            _remove_handler(root_logger, handler)


def _remove_handler(root_logger: logging.Logger, handler: logging.Handler):
    """핸들러 제거"""
    root_logger.removeHandler(handler)
    try:
        handler.close()
    except Exception:
        pass


def _configure_mcp_loggers():
    """MCP 관련 로거 레벨 설정"""
    mcp_loggers = [
        "src.capabilities.servers.external.mcp_client",
        "src.capabilities.servers.external.client_manager",
        "src.capabilities.mcp_service",
        "src.capabilities.logging_utils",
    ]
    for logger_name in mcp_loggers:
        mcp_logger = logging.getLogger(logger_name)
        mcp_logger.setLevel(logging.DEBUG)


def _clear_existing_handlers(root_logger: logging.Logger):
    """기존 핸들러 제거"""
    existing_handlers = list(root_logger.handlers)
    for handler in existing_handlers:
        _remove_handler(root_logger, handler)
    if len(root_logger.handlers) > 0:
        root_logger.handlers.clear()


# 로깅 설정 실행
setup_logging()
logger = getLogger("api")


# ============================================================================
# 시그널 핸들러
# ============================================================================

def signal_handler(signum, frame):
    """시그널 핸들러 - graceful shutdown"""
    logger.info(f"[MAIN] 시그널 {signum} 수신, 애플리케이션 종료 중...")

    try:
        from src.memory.memory_manager import memory_manager
        memory_manager.close()
        logger.debug("[MAIN] 메모리 매니저가 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] 메모리 매니저 종료 중 오류: {e}")

    try:
        from src.database.connection import close_connections
        close_connections()
        logger.debug("[MAIN] 데이터베이스 연결이 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] 데이터베이스 연결 종료 중 오류: {e}")

    logger.debug("[MAIN] 애플리케이션 종료 완료")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ============================================================================
# 로거 설정
# ============================================================================

_noisy_loggers = [
    "openai",
    "openai._base_client",
    "httpx",
    "httpcore",
    "urllib3",
    "watchfiles.main",
]

for name in _noisy_loggers:
    try:
        nl = logging.getLogger(name)
        nl.setLevel(logging.WARNING)
        nl.propagate = False
    except Exception:
        pass


# ============================================================================
# 미들웨어
# ============================================================================

class SessionCookieMiddleware(BaseHTTPMiddleware):
    """세션 쿠키 관리 미들웨어"""

    def __init__(self, app):
        super().__init__(app)
        self.cookie_name = os.getenv("SESSION_COOKIE_NAME", "sid")
        self.cookie_secure = (
            os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
        )
        self.cookie_samesite = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()
        self.cookie_max_age = int(os.getenv("SESSION_COOKIE_MAX_AGE", "2592000"))

    async def dispatch(self, request, call_next):
        sid = request.cookies.get(self.cookie_name)
        new_sid = False
        if not sid or len(str(sid).strip()) == 0:
            sid = uuid.uuid4().hex
            new_sid = True
        response: Response = await call_next(request)
        if new_sid:
            response.set_cookie(
                key=self.cookie_name,
                value=sid,
                httponly=True,
                secure=self.cookie_secure,
                samesite=(
                    "lax"
                    if self.cookie_samesite not in ("lax", "strict", "none")
                    else self.cookie_samesite
                ),
                max_age=self.cookie_max_age,
                path="/",
            )
        return response


class DebugLogCollectorMiddleware(BaseHTTPMiddleware):
    """디버그 로그 수집 미들웨어"""

    def __init__(self, app):
        super().__init__(app)
        self.debug_flag = False  # ⚠️ os.env로 두기

    async def dispatch(self, request, call_next):
        """요청이 들어오면 Collector 초기화 후 필요시 활성화"""
        if self.debug_flag:
            collector.enable()
        else:
            collector.disable()
        return await call_next(request)


# ============================================================================
# 에이전트 및 워크플로우 등록
# ============================================================================

class OrchestratorFactory:
    """에이전트별 오케스트레이터를 생성하는 팩토리 클래스"""

    @classmethod
    def get_orchestrator(cls, agent_code: str):
        """에이전트 코드에 따라 적절한 오케스트레이터를 반환"""
        from src.orchestration.common.workflow_registry import workflow_registry

        orchestrator = workflow_registry.get_orchestrator(agent_code)
        if orchestrator:
            return orchestrator

        active_agent_code = get_active_agent_code()
        if active_agent_code:
            logger.error(
                f"[ORCHESTRATOR_FACTORY] {agent_code.upper()} 에이전트가 등록되지 않았습니다. "
                f"현재 단일 에이전트 모드로 {active_agent_code.upper()}만 활성화되어 있습니다."
            )
            raise ValueError(
                f"Agent '{agent_code}' is not registered. "
                f"Only '{active_agent_code}' is active in single-agent mode."
            )

        default_agent = workflow_registry.get_default_agent()
        if default_agent:
            return workflow_registry.get_orchestrator(default_agent)

        logger.warning(
            f"[ORCHESTRATOR_FACTORY] {agent_code.upper()} 에이전트를 찾을 수 없어 CAIA로 fallback"
        )
        return workflow_registry.get_orchestrator("caia")


def register_agent_workflow(
    agent_code: str,
    orchestrator_class,
    state_builder_class,
    response_handler_class=None,
):
    """
    에이전트 워크플로우를 모든 레지스트리에 등록하는 헬퍼 함수

    Args:
        agent_code: 에이전트 코드 (예: "caia", "raih")
        orchestrator_class: 오케스트레이터 클래스
        state_builder_class: 상태 빌더 클래스
        response_handler_class: 응답 처리기 클래스 (선택적)
    """
    from src.orchestration.common.workflow_registry import workflow_registry
    from src.orchestration.common.agent_interface import orchestration_registry

    orchestrator = orchestrator_class()
    state_builder = state_builder_class()
    workflow_registry.register_orchestrator(agent_code, orchestrator)
    workflow_registry.register_state_builder(agent_code, state_builder)

    if response_handler_class:
        response_handler = response_handler_class(logger=logger)
        orchestration_registry.register_response_handler(agent_code, response_handler)


# 에이전트 등록 매핑
_AGENT_REGISTRY = {
    "caia": CAIAAgent,
    "raih": RAIHAgent,
    "lexai": LexAIAgent,
}

# 워크플로우 등록 매핑
_WORKFLOW_REGISTRY = {
    "caia": {
        "orchestrator": "src.orchestration.caia.caia_orchestrator.CAIAOrchestrator",
        "state_builder": "src.orchestration.caia.caia_state_builder.CAIAStateBuilder",
        "response_handler": "src.orchestration.caia.caia_response_handler.CAIAResponseHandler",
    },
    "raih": {
        "orchestrator": "src.orchestration.raih.raih_orchestrator.RAIHOrchestrator",
        "state_builder": "src.orchestration.raih.raih_state_builder.RAIHStateBuilder",
        "response_handler": "src.orchestration.raih.raih_response_handler.RAIHResponseHandler",
    },
    "lexai": {
        "orchestrator": "src.orchestration.lexai.lexai_orchestrator.LexAIOrchestrator",
        "state_builder": "src.orchestration.lexai.lexai_state_builder.LexAIStateBuilder",
        "response_handler": "src.orchestration.lexai.lexai_response_handler.LexAIResponseHandler",
    },
}


def register_agents():
    """에이전트 레지스트리 초기화"""
    logger.info("[MAIN] 에이전트 레지스트리 초기화 시작...")

    active_agent_code = get_active_agent_code()
    agents_to_register = [active_agent_code] if active_agent_code else list(_AGENT_REGISTRY.keys())

    if active_agent_code:
        logger.info(
            f"[MAIN] 단일 에이전트 모드: {active_agent_code.upper()}만 등록합니다."
        )

    for agent_code in agents_to_register:
        if agent_code not in _AGENT_REGISTRY:
            logger.warning(
                f"[MAIN] 알 수 없는 에이전트 코드: {agent_code}. 모든 에이전트를 등록합니다."
            )
            agents_to_register = list(_AGENT_REGISTRY.keys())
            break

    for agent_code in agents_to_register:
        agent_class = _AGENT_REGISTRY[agent_code]
        agent_registry.register_agent(agent_class())
        logger.info(f"[MAIN] {agent_code.upper()} 에이전트 등록 완료")

    logger.info("[MAIN] 에이전트 레지스트리 초기화 완료")


def register_workflows(app: FastAPI):
    """워크플로우 레지스트리 초기화"""
    logger.info("[MAIN] 워크플로우 레지스트리 초기화 시작...")

    try:
        from src.orchestration.common.agent_interface import orchestration_registry

        active_agent_code = get_active_agent_code()
        workflows_to_register = (
            [active_agent_code] if active_agent_code else list(_WORKFLOW_REGISTRY.keys())
        )

        if active_agent_code:
            logger.info(
                f"[MAIN] 단일 에이전트 모드: {active_agent_code.upper()} 워크플로우만 등록합니다."
            )

        for agent_code in workflows_to_register:
            if agent_code not in _WORKFLOW_REGISTRY:
                logger.warning(
                    f"[MAIN] 알 수 없는 에이전트 코드: {agent_code}. 모든 워크플로우를 등록합니다."
                )
                workflows_to_register = list(_WORKFLOW_REGISTRY.keys())
                break

        for agent_code in workflows_to_register:
            workflow_config = _WORKFLOW_REGISTRY[agent_code]

            # 동적 임포트
            from importlib import import_module

            orchestrator_module_path, orchestrator_class_name = workflow_config[
                "orchestrator"
            ].rsplit(".", 1)
            state_builder_module_path, state_builder_class_name = workflow_config[
                "state_builder"
            ].rsplit(".", 1)
            response_handler_module_path, response_handler_class_name = workflow_config[
                "response_handler"
            ].rsplit(".", 1)

            orchestrator_module = import_module(orchestrator_module_path)
            state_builder_module = import_module(state_builder_module_path)
            response_handler_module = import_module(response_handler_module_path)

            orchestrator_class = getattr(orchestrator_module, orchestrator_class_name)
            state_builder_class = getattr(state_builder_module, state_builder_class_name)
            response_handler_class = getattr(
                response_handler_module, response_handler_class_name
            )

            register_agent_workflow(
                agent_code=agent_code,
                orchestrator_class=orchestrator_class,
                state_builder_class=state_builder_class,
                response_handler_class=response_handler_class,
            )

        app.state.orchestration_registry = orchestration_registry
        logger.info("[MAIN] 워크플로우 레지스트리 초기화 완료")

    except Exception as e:
        logger.error(f"[MAIN] 워크플로우 레지스트리 초기화 실패: {e}", exc_info=True)
        raise


# ============================================================================
# 애플리케이션 초기화
# ============================================================================

async def initialize_llm(config: dict):
    """LLM 매니저 초기화"""
    if not llm_manager.is_initialized:
        llm_cfg = config.get("llm", {})
        await llm_manager.initialize(llm_cfg if isinstance(llm_cfg, dict) else {})
        if not llm_manager.is_initialized:
            logger.error("[MAIN] LLM 매니저 초기화 실패!")


async def initialize_memory(config: dict):
    """메모리 매니저 초기화"""
    mem_cfg = config.get("memory", {}) if isinstance(config, dict) else {}
    mm_config = {
        "provider_type": str(mem_cfg.get("provider", "mysql")),
        "database_url": mem_cfg.get("database_url") or os.getenv("DATABASE_URL"),
        "redis_url": mem_cfg.get("redis_url")
        or os.getenv("REDIS_URL")
        or os.getenv("MEMORY_REDIS_URL"),
    }
    initialize_memory_manager(mm_config)


async def initialize_tools(config: dict):
    """ToolRegistry 초기화"""
    tr_cfg = config.get("tools", {}) if isinstance(config, dict) else {}
    ToolRegistry.initialize(path=tr_cfg.get("registry_yaml"))


async def initialize_sse_logging():
    """SSE 로깅 설정"""
    from .logging.sse_log_handler import setup_sse_logging
    setup_sse_logging()
    logger.debug("[MAIN] SSE 로깅이 설정되었습니다.")


async def initialize_stream_manager():
    """스트림 매니저 초기화"""
    from .routers.chat.stream_manager import stream_manager
    await stream_manager.start_cleanup_task()
    logger.debug("[MAIN] 스트림 매니저가 초기화되었습니다.")


async def initialize_mcp_service():
    """MCP 서비스 초기화"""
    try:
        from src.capabilities.mcp_service import mcp_service
        from src.capabilities.servers.external.client_manager import mcp_manager

        await mcp_service.initialize()
        clients = list(mcp_manager.clients.keys())
        if not clients:
            logger.warning(
                "[MAIN] MCP 클라이언트가 등록되지 않았습니다. "
                "lgenie_mcp 설정을 확인하세요."
            )
    except Exception as e:
        logger.warning(f"[MAIN] MCP 서비스 초기화 실패: {e}")


async def shutdown_services():
    """서비스 종료"""
    logger.info("[MAIN] 애플리케이션 종료 중...")

    try:
        await llm_manager.close()
        logger.debug("[MAIN] LLM 매니저가 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] LLM 매니저 종료 중 오류: {e}")

    try:
        from src.memory.memory_manager import memory_manager
        memory_manager.close()
        logger.debug("[MAIN] 메모리 매니저가 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] 메모리 매니저 종료 중 오류: {e}")

    try:
        from src.capabilities.mcp_service import mcp_service
        await mcp_service.close()
        logger.debug("[MAIN] MCP 서비스가 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] MCP 서비스 종료 중 오류: {e}")

    try:
        from src.database.connection import close_connections
        close_connections()
        logger.debug("[MAIN] 데이터베이스 연결이 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] 데이터베이스 연결 종료 중 오류: {e}")

    try:
        from .routers.chat.stream_manager import stream_manager
        await stream_manager.cleanup()
        logger.debug("[MAIN] 스트림 매니저가 종료되었습니다.")
    except Exception as e:
        logger.error(f"[MAIN] 스트림 매니저 종료 중 오류: {e}")

    logger.info("[MAIN] 애플리케이션 종료 완료")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup/shutdown 훅"""
    logger.info("[MAIN] 애플리케이션 시작...")
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)

    # 설정 로드
    config = load_config()

    # 초기화 작업
    await initialize_llm(config)
    await initialize_tools(config)
    await initialize_memory(config)
    register_agents()
    register_workflows(app)

    # LLM 설정 업데이트
    from configs.app_config import _update_llm_config_from_db
    _update_llm_config_from_db(config)
    logger.info("[MAIN] LLM 설정 업데이트 완료")

    # 오케스트레이터 팩토리 준비
    app.state.orchestrator_factory = OrchestratorFactory
    logger.debug(
        "[MAIN] 오케스트레이터 팩토리가 성공적으로 생성되어 app.state에 저장되었습니다."
    )

    # 추가 초기화
    await initialize_sse_logging()
    await initialize_stream_manager()
    await initialize_mcp_service()

    yield

    # 종료
    await shutdown_services()


# ============================================================================
# FastAPI 앱 생성
# ============================================================================

app = FastAPI(
    title="Expert Agents API",
    description="""
    ## AI 에이전트 서비스 관리 API
    
    다양한 AI 에이전트와 실시간 채팅을 제공하는 서비스입니다.
    
    ### 주요 기능
    - **실시간 채팅**: SSE(Server-Sent Events)를 통한 스트리밍 응답
    - **다중 에이전트**: CAIA, Discussion, Search 등 다양한 에이전트 지원
    - **채팅 관리**: 채팅 채널 및 메시지 히스토리 관리
    - **메모리 시스템**: STM(Redis) + LTM(MySQL) 기반 컨텍스트 유지
    - **실시간 로깅**: 서버 로그 실시간 스트리밍
    - **SSO 인증**: 쿠키 기반 엘지니 SSO 통합 인증
    - **MCP 통합**: Model Context Protocol을 통한 엘지니 툴 연동
    
    ### 지원 에이전트
    - **CAIA (Chief AI Advisor)**: C레벨 임원전용 AI 어드바이저
    - **Discussion**: 심화 분석 및 토론형 대화
    - **Search**: 웹 검색 기반 정보 제공
    
    ### API 엔드포인트
    - **채팅**: `/{agent_code}/stream` - 실시간 채팅 스트리밍
    - **채팅 관리**: `/api/v1/chat/*` - 채팅 채널 및 메시지 관리
    - **인증**: `/{agent_code}/auth/*` - SSO 로그인 및 인증
    - **메모리**: `/api/v1/memory/*` - 사용자 메모리 관리
    - **로그**: `/logs/stream` - 실시간 로그 스트리밍
    - **상태**: `/health`, `/{agent_code}/health` - 서비스 상태 확인
    
    ### API 사용법
    1. **채팅 요청**: 에이전트 코드를 URL 경로에 포함하여 요청
    2. **요청 형식**: 간소화된 JSON 형식으로 채팅 요청 전송
    3. **응답 수신**: SSE 스트림으로 실시간 응답 수신
    4. **세션 관리**: `chat_group_id`로 채팅 세션 관리
    5. **인증**: SSO 쿠키 기반 자동 인증
    
    ### 데이터베이스 스키마
    - **ChatChannel**: 채팅 채널 정보
    - **ChatMessage**: 채팅 메시지 히스토리
    - **User**: 사용자 정보
    - **Agent**: 에이전트 정보
    - **Memory**: 사용자 메모리 데이터
    """,
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "deepLinking": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 1,
        "defaultModelRendering": "example",
        "showRequestHeaders": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True,
        "requestInterceptor": """
        function(request) {
            if (!request.headers) {
                request.headers = {};
            }
            request.headers['Accept'] = request.headers['Accept'] || 'application/json, text/plain, */*';
            request.headers['Accept-Encoding'] = request.headers['Accept-Encoding'] || 'gzip, deflate, br, zstd';
            request.headers['Accept-Language'] = request.headers['Accept-Language'] || 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7';
            request.headers['Cache-Control'] = request.headers['Cache-Control'] || 'no-cache';
            request.headers['Connection'] = request.headers['Connection'] || 'keep-alive';
            request.headers['Content-Type'] = request.headers['Content-Type'] || 'application/json';
            if (request.url.includes('/stream')) {
                request.headers['Accept'] = 'text/event-stream';
                request.headers['Cache-Control'] = 'no-cache';
            }
            return request;
        }
        """,
        "responseInterceptor": """
        function(response) {
            if (response.url.includes('/stream')) {
                console.log('SSE Stream Response:', response);
            }
            return response;
        }
        """,
    },
)

# 미들웨어 등록
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionCookieMiddleware)
app.add_middleware(DebugLogCollectorMiddleware)

# 라우터 등록
app.include_router(base_router)
app.include_router(agent_router)
app.include_router(agent_auth_router)
app.include_router(agents_list_router)
app.include_router(memory_router)
app.include_router(log_router)
app.include_router(chat_management_router)
app.include_router(lexai_router)

from src.apps.api.routers.api_key_router import api_key_router

app.include_router(api_key_router)


# ============================================================================
# LexAI 전용 Swagger 문서 앱
# ============================================================================

lexai_docs_app = FastAPI(
    title="LexAI API",
    description="""
    ## LexAI - 법령 개정 분석 API
    
    법령 개정 내용을 분석하여 사내 규정 변경 조언을 제공하는 API입니다.
    
    ### 주요 기능
    - **법령 개정 분석**: 법령 개정 내용을 분석하여 사내 규정 변경 조언 생성
    - **정합성 체크**: 완료된 분석 결과를 조회하여 정합성 체크 결과 반환
    
    ### API 엔드포인트
    - **법령 개정 분석**: `POST /lexai/api/v1/analyze` - 법령 개정 내용 분석 및 규정 변경 조언 생성
    - **정합성 체크 조회**: `POST /lexai/api/v1/consistency-check` - 완료된 분석 결과 조회
    
    ### 인증
    모든 API는 **X-API-Key** 헤더에 유효한 API Key를 포함해야 합니다.
    API Key는 관리자에게 문의하여 발급받을 수 있습니다.
    
    ### 사용 방법
    1. API Key를 발급받습니다
    2. 요청 시 `X-API-Key` 헤더에 API Key를 포함합니다
    3. 법령 개정 분석 API로 분석 요청
    4. 분석 완료 후 정합성 체크 API로 결과 조회
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "showExtensions": True,
        "showCommonExtensions": True,
        "deepLinking": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 1,
        "defaultModelRendering": "example",
        "showRequestHeaders": True,
        "showCommonExtensions": True,
        "tryItOutEnabled": True,
    },
)


def custom_openapi_lexai():
    """LexAI 전용 OpenAPI 스키마에 API Key 인증 추가"""
    if lexai_docs_app.openapi_schema:
        return lexai_docs_app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=lexai_docs_app.title,
        version=lexai_docs_app.version,
        description=lexai_docs_app.description,
        routes=lexai_docs_app.routes,
    )

    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "LexAI API Key. 관리자에게 문의하여 발급받을 수 있습니다.",
        }
    }

    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                if "security" not in operation:
                    operation["security"] = [{"ApiKeyAuth": []}]

    lexai_docs_app.openapi_schema = openapi_schema
    return lexai_docs_app.openapi_schema


lexai_docs_app.openapi = custom_openapi_lexai
lexai_docs_app.include_router(lexai_router)
app.mount("/lexai_docs", lexai_docs_app)
app.mount("/docs/lexai", lexai_docs_app)


# ============================================================================
# 메인 실행
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # 직접 실행 시 콘솔 로깅 활성화
    if os.getenv("ENABLE_CONSOLE_LOGGING") is None:
        os.environ["ENABLE_CONSOLE_LOGGING"] = "true"
        setup_logging()

    reload_flag = os.getenv("APP_RELOAD", "false").lower() == "true"
    uvicorn_reload = os.getenv("UVICORN_RELOAD", "false").lower() == "true"

    project_root = get_project_root()
    default_reload_dir = os.path.join(project_root, "src")

    reload_dirs_env = os.getenv("UVICORN_RELOAD_DIRS", default_reload_dir)
    reload_dirs = [d.strip() for d in reload_dirs_env.split(",") if d.strip()]

    reload_config = {
        "reload": reload_flag or uvicorn_reload,
        "reload_dirs": reload_dirs if reload_dirs else [default_reload_dir],
        "reload_delay": 0.25,
        "reload_includes": ["*.py"],
        "reload_excludes": ["*.pyc", "__pycache__", "*.log"],
    }

    uvicorn.run(
        "src.apps.api.main:app",
        host="0.0.0.0",
        port=8000,
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
        log_config=None,
        **reload_config,
    )
