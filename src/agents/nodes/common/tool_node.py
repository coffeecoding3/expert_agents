"""
Tool Node for Agent Graph
에이전트 그래프의 도구 실행 노드
"""

from logging import getLogger
from typing import Any, Dict, List

logger = getLogger("agents.tool_node")


class ToolNode:
    """도구 실행 노드"""

    def __init__(self, tools: List[Any]):
        """
        초기화

        Args:
            tools: 사용 가능한 도구 목록
        """
        self.tools = {}
        for tool in tools:
            # tool.name이 없으면 클래스 이름을 사용
            tool_name = getattr(tool, "name", None) or tool.__class__.__name__
            self.tools[tool_name] = tool

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        주어진 상태에 따라 적절한 도구를 실행합니다.

        Args:
            state: 현재 에이전트 상태

        Returns:
            도구 실행 결과를 포함하는 업데이트된 상태
        """
        logger.info("[TOOLNODE] 도구 실행을 시작합니다")
        # TODO: 상태에서 도구 이름과 인자를 추출하여 실행하는 로직 구현
        tool_name = state.get("tool_to_execute")
        tool_input = state.get("tool_input")

        if tool_name and tool_name in self.tools:
            try:
                tool = self.tools[tool_name]
                logger.info(f"[TOOLNODE] {tool_name} 도구를 실행합니다")
                logger.debug(
                    "[TOOLNODE] run tool=%s input_keys=%s",
                    tool_name,
                    (
                        list(tool_input.keys())
                        if isinstance(tool_input, dict)
                        else type(tool_input).__name__
                    ),
                )
                result = await tool.run(tool_input)
                try:
                    preview = str(result)[:300]
                except Exception:
                    preview = "<unprintable>"
                logger.info(f"[TOOLNODE] {tool_name} 도구 실행이 완료되었습니다")
                logger.debug(
                    "[TOOLNODE] run:end tool=%s result_preview=%s", tool_name, preview
                )
                return {"tool_output": result}
            except Exception as e:
                logger.error(f"[TOOLNODE] run:error {e}")
                return {"tool_output": f"Error: {e}"}

        logger.warning("[TOOLNODE] 실행할 유효한 도구가 없습니다")
        return {"tool_output": "No tool executed."}
