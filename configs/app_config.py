"""
Application Configuration Loader
YAML 설정 파일을 로드하고 관리합니다.
"""

import logging
import yaml
from pathlib import Path
import os
import re
from typing import Dict, Any, Optional

CONFIG_FILE_PATH = Path(__file__).parent / "app.yaml"
logger = logging.getLogger("app_config")

# 설정 캐시
_config_cache: Optional[Dict[str, Any]] = None
_db_config_updated: bool = False


def load_env_file(env_path: Path) -> None:
    """
    .env 파일을 로드하여 환경 변수로 설정합니다.
    """
    if not env_path.is_file():
        return

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and not os.getenv(key):  # 이미 설정된 환경변수는 덮어쓰지 않음
                    os.environ[key] = value


def substitute_env_vars(text: str) -> str:
    """
    텍스트 내의 ${VAR_NAME} 또는 ${VAR_NAME:-default} 형식의 환경 변수를 치환합니다.
    환경 변수가 설정되어 있지 않으면 기본값을 사용하거나, 기본값이 없으면 원래의 플레이스홀더를 반환합니다.
    """

    def replace_var(match):
        var_spec = match.group(1)
        if ":-" in var_spec:
            var_name, default_value = var_spec.split(":-", 1)
            return os.getenv(var_name, default_value)
        else:
            var_name = var_spec
            return os.getenv(var_name, match.group(0))

    return re.sub(r"\$\{([^}]+)\}", replace_var, text)


def load_config() -> dict:
    """
    app.yaml 설정 파일을 로드합니다.
    환경 변수를 사용하여 일부 설정을 오버라이드할 수 있습니다.
    캐시를 사용하여 중복 로드를 방지합니다.
    """
    global _config_cache, _db_config_updated
    
    # 캐시가 있으면 반환
    if _config_cache is not None:
        return _config_cache
    
    if not CONFIG_FILE_PATH.is_file():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {CONFIG_FILE_PATH}")

    with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 먼저 .env 파일 경로를 찾기 위해 기본 YAML 파싱 (환경변수 치환 없이)
    temp_config = yaml.safe_load(content)
    env_file_path_raw = temp_config.get("env_file")

    # env_file 경로도 환경변수 치환 필요
    env_file_path = (
        substitute_env_vars(env_file_path_raw) if env_file_path_raw else None
    )

    # .env 파일이 있으면 먼저 로드
    if env_file_path:
        # 상대 경로를 절대 경로로 변환
        if not Path(env_file_path).is_absolute():
            env_file_path = CONFIG_FILE_PATH.parent / env_file_path

        load_env_file(Path(env_file_path))

    # .env 파일 로드 후 환경변수 치환
    content = substitute_env_vars(content)
    config = yaml.safe_load(content)

    # agent_llm_config 테이블에서 LLM 설정 읽어서 업데이트 (한 번만 실행)
    if not _db_config_updated:
        _update_llm_config_from_db(config)
        _db_config_updated = True

    # lgenie_mcp_config = config.get("lgenie_mcp", {})
    # if "endpoint" in lgenie_mcp_config:
    #     lgenie_mcp_config["endpoint"] = os.getenv(
    #         "LGENIE_MCP_ENDPOINT", lgenie_mcp_config.get("endpoint")
    #     )
    # if "api_key" in lgenie_mcp_config:
    #     lgenie_mcp_config["api_key"] = os.getenv(
    #         "LGENIE_MCP_API_KEY", lgenie_mcp_config.get("api_key")
    #     )
    # if "retry_attempts" in lgenie_mcp_config:
    #     lgenie_mcp_config["retry_attempts"] = os.getenv(
    #         "LGENIE_MCP_RETRY_ATTEMPTS", lgenie_mcp_config.get("retry_attempts")
    #     )

    # 캐시에 저장
    _config_cache = config
    return config


def _update_llm_config_from_db(config: Dict[str, Any]) -> None:
    """
    agent_llm_config 테이블에서 LLM 설정을 읽어서 config의 llm.providers.openai 설정을 업데이트합니다.
    DB 연결이 불가능한 경우 무시합니다.
    """
    try:
        # DB 연결 시도 (순환 참조 방지를 위해 여기서 import)
        from src.database.connection import get_db
        from src.database.services.agent_services import agent_llm_config_service
        from src.database.models.agent import AgentLLMConfig

        db = next(get_db())
        try:
            # provider가 "openai"인 활성화된 LLM 설정 조회
            llm_configs = (
                db.query(AgentLLMConfig)
                .filter(
                    AgentLLMConfig.provider == "openai",
                    AgentLLMConfig.is_active == True,
                )
                .all()
            )

            if not llm_configs:
                logger.debug("[APP_CONFIG] agent_llm_config에서 openai 설정을 찾을 수 없습니다.")
                return

            # 첫 번째 설정 사용 (또는 우선순위에 따라 선택)
            llm_config = llm_configs[0]
            
            # llm.providers.openai 설정 초기화 또는 가져오기
            if "llm" not in config:
                config["llm"] = {}
            if "providers" not in config["llm"]:
                config["llm"]["providers"] = {}
            if "openai" not in config["llm"]["providers"]:
                config["llm"]["providers"]["openai"] = {}

            openai_config = config["llm"]["providers"]["openai"]

            # config_json에서 설정 읽기
            config_json = llm_config.config_json or {}
            
            # DB 설정으로 업데이트 (기존 설정보다 우선)
            if config_json.get("api_key"):
                openai_config["api_key"] = config_json["api_key"]
            if config_json.get("base_url"):
                openai_config["base_url"] = config_json["base_url"]
            if config_json.get("api_version"):
                openai_config["api_version"] = config_json["api_version"]
            if config_json.get("deployment"):
                openai_config["deployment"] = config_json["deployment"]
            if config_json.get("organization"):
                openai_config["organization"] = config_json["organization"]
            
            # model 필드도 설정에 추가
            if llm_config.model:
                openai_config["model_name"] = llm_config.model
                if not openai_config.get("deployment"):
                    openai_config["deployment"] = llm_config.model

            logger.info(
                f"[APP_CONFIG] agent_llm_config에서 LLM 설정을 로드했습니다. "
                f"(agent_id={llm_config.agent_id}, model={llm_config.model})"
            )

        finally:
            db.close()

    except Exception as e:
        # DB 연결 실패 시 무시 (초기화 단계에서 DB가 아직 준비되지 않았을 수 있음)
        logger.debug(f"[APP_CONFIG] agent_llm_config에서 설정을 로드할 수 없습니다: {e}")


def clear_config_cache() -> None:
    """
    설정 캐시를 초기화합니다.
    테스트나 설정 변경 후 재로드가 필요한 경우 사용합니다.
    """
    global _config_cache, _db_config_updated
    _config_cache = None
    _db_config_updated = False
