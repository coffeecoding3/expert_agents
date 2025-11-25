"""
룰 기반 Tool 결과 변환기
"""

import logging
from typing import Any, Dict, List, Optional

from src.schemas.tool_result_schema import ToolResultConverter, UnifiedToolResult
from src.utils.log_collector import collector

logger = logging.getLogger("tool_result_converter")


class ToolResultConverter:
    """룰 기반으로 Tool 결과를 통일된 스키마로 변환하는 클래스"""

    def __init__(self):
        self.logger = logger

    def convert_tool_result(
        self,
        tool_result: Dict[str, Any],
        query: str = "",
        user_context: Optional[Dict[str, Any]] = None,
    ) -> UnifiedToolResult:
        """
        룰 기반으로 tool 결과를 통일된 스키마로 변환

        Args:
            tool_result: 기존 tool 결과 딕셔너리
            query: 검색 쿼리 (사용하지 않음, 호환성을 위해 유지)
            user_context: 사용자 컨텍스트 (사용하지 않음, 호환성을 위해 유지)

        Returns:
            UnifiedToolResult: 통일된 스키마의 결과
        """
        try:
            # ToolResultConverter의 정적 메소드 사용
            from src.schemas.tool_result_schema import (
                ToolResultConverter as SchemaConverter,
            )

            unified_result = SchemaConverter.convert_tool_result(tool_result)

            return unified_result

        except Exception as e:
            self.logger.error(
                f"[TOOL_CONVERTER] 변환 실패: {tool_result.get('tool', 'unknown')} - {e}"
            )
            # 변환 실패 시 기본 결과 반환
            return UnifiedToolResult(
                tool_name=tool_result.get("tool", "unknown"),
                raw_result=tool_result.get("result"),
                formatted_result=str(tool_result.get("result", "")),
            )

    def convert_multiple_tool_results(
        self,
        tool_results: List[Dict[str, Any]],
        query: str = "",
        user_context: Optional[Dict[str, Any]] = None,
    ) -> List[UnifiedToolResult]:
        """여러 tool 결과를 일괄 변환"""
        unified_results = []

        for i, tool_result in enumerate(tool_results):
            try:
                unified_result = self.convert_tool_result(
                    tool_result, query, user_context
                )
                unified_results.append(unified_result)

                # 로그 수집
                collector.log(
                    "tool_conversion",
                    {
                        "tool_name": unified_result.tool_name,
                        "conversion_method": "rule_based",
                    },
                )

            except Exception as e:
                self.logger.error(
                    f"[TOOL_CONVERTER] 개별 변환 실패 ({i+1}/{len(tool_results)}): {e}"
                )
                # 개별 변환 실패 시 기본 결과 사용
                fallback_result = UnifiedToolResult(
                    tool_name=tool_result.get("tool", "unknown"),
                    raw_result=tool_result.get("result"),
                    formatted_result=str(tool_result.get("result", "")),
                )
                unified_results.append(fallback_result)

        return unified_results
