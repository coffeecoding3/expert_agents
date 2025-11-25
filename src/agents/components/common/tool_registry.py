"""
Tool Registry

의도분석/플래닝을 위해 공개할 수 있는 도구 스키마와 제약을 중앙에서 관리하며,
실제 `agents.tools` 디렉토리의 툴 클래스들을 자동으로 탐색해 메타데이터를 생성합니다.

역할:
1. `agents.tools` 패키지에서 BaseTool을 상속한 도구 클래스들을 자동 탐색
2. tool_registry.yaml 파일의 스키마 정의와 병합
3. 의도 분석 및 플래닝에 사용할 도구 메타데이터 제공

관련 파일:
- tool_registry.yaml: 도구 스키마 및 제약 조건 정의
- capabilities/registry.yaml: MCP 서버 설정 (별도 관리)
"""

import importlib
import inspect
import os
import pkgutil
from typing import Any, Dict, List, Type

import yaml


class ToolRegistry:
    _yaml_path: str | None = None

    @staticmethod
    def initialize(path: str | None = None) -> None:
        """외부에서 레지스트리 YAML 경로를 주입.
        path가 None이면 환경변수/기본 경로 사용."""
        ToolRegistry._yaml_path = path

    @staticmethod
    def _discover_tool_classes() -> List[Type[Any]]:
        """`agents.tools` 패키지에서 툴 클래스를 동적으로 탐색."""
        discovered: List[Type[Any]] = []

        # 탐색할 서브패키지들
        subpackages = ["caia", "search_agent", "common", "mcp"]

        for subpackage in subpackages:
            try:
                pkg = importlib.import_module(f"src.agents.tools.{subpackage}")
                for m in pkgutil.iter_modules(pkg.__path__):  # type: ignore[arg-type]
                    try:
                        mod = importlib.import_module(
                            f"src.agents.tools.{subpackage}.{m.name}"
                        )
                    except Exception:
                        continue
                    for _, obj in inspect.getmembers(mod, inspect.isclass):
                        # 클래스가 해당 모듈에 정의되고, name/description/run을 보유
                        if obj.__module__ != mod.__name__:
                            continue
                        if (
                            hasattr(obj, "name")
                            and hasattr(obj, "description")
                            and hasattr(obj, "run")
                        ):
                            discovered.append(obj)
            except Exception:
                pass
        return discovered

    @staticmethod
    def get_tool_instances() -> List[Any]:
        """탐색된 툴 클래스들을 인스턴스화하여 반환."""
        instances: List[Any] = []
        for cls in ToolRegistry._discover_tool_classes():
            try:
                instances.append(cls())
            except Exception:
                continue

        return instances

    @staticmethod
    def _describe_tool(instance: Any) -> Dict[str, Any]:
        """툴 인스턴스로부터 메타데이터를 생성합니다."""
        tool_name = getattr(instance, "name", None) or instance.__class__.__name__
        description = getattr(instance, "description", "")
        meta = {"tool_name": tool_name, "description": description}
        return meta

    @staticmethod
    def get_available_tools() -> List[Dict[str, Any]]:
        """의도분석에 제공할 도구 메타데이터 목록 반환.

        우선순위:
        1) YAML 오버라이드 파일이 있으면 이를 병합해 사용
        2) 코드 내 탐색 + 오버라이드 병합
        """
        tools: List[Dict[str, Any]] = []
        for inst in ToolRegistry.get_tool_instances():
            tools.append(ToolRegistry._describe_tool(inst))

        # YAML 오버라이드 병합
        override_path_env = os.getenv("TOOL_REGISTRY_YAML")
        default_path = os.path.join(os.path.dirname(__file__), "tool_registry.yaml")
        yaml_path = ToolRegistry._yaml_path or override_path_env or default_path
        try:
            if os.path.exists(yaml_path):
                with open(yaml_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    by_name: Dict[str, Dict[str, Any]] = {
                        t.get("tool_name"): t for t in tools
                    }
                    for item in data.get("tools", []):
                        name = item.get("tool_name")
                        if not name:
                            continue
                        if name in by_name:
                            by_name[name].update(item)
                        else:
                            by_name[name] = item
                    tools = list(by_name.values())
        except Exception:
            pass

        return tools
