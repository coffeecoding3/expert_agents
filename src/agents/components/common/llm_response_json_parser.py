"""
LLM Response JSON Parser

LLM 응답 문자열에서 JSON을 안전하게 추출/복구/검증하기 위한 유틸
"""

from __future__ import annotations

import json
import re
from typing import Any, Union

try:
    import json5  # type: ignore
except (
    Exception
):  # pragma: no cover - optional dependency may not be available in some envs
    json5 = None  # type: ignore

try:
    from jsonschema import ValidationError  # type: ignore
    from jsonschema import validate  # type: ignore
except (
    Exception
):  # pragma: no cover - optional dependency may not be available in some envs
    validate = None  # type: ignore

    class ValidationError(Exception):  # type: ignore
        pass


class LLMResponseJsonParser:
    def __init__(
        self, fallback_response: Union[dict, list], schema: dict | None = None
    ):
        """
        :param schema: JSON 구조 검증용 스키마
        :param fallback_response: 실패시 반환할 default 응답
        """
        if fallback_response is None:
            raise ValueError("fallback_response는 필수값입니다.")
        self.fallback_response = fallback_response
        self.schema = schema
        self.last_stage: str | None = None  # for debugging

    def parse(self, text: str) -> Union[dict, list]:
        if not text:
            raise ValueError("LLM 응답(text)은 필수값입니다.")

        # 1. 가장 큰 JSON-like block 추출
        data = self._extract_json_block(text)

        # 2. JSON Repair
        data = self._repair_json(data)

        # 3. Strict JSON Parsing
        parsed = self._strict_parse(data)
        self.last_stage = "strict_parse"

        # 4. Lenient Parsing
        if parsed is None:
            parsed = self._lenient_parse(data)
            self.last_stage = "lenient_parse"

        # 5. Schema Validation
        if parsed is not None and self.schema is not None and validate is not None:
            try:
                validate(instance=parsed, schema=self.schema)
            except ValidationError:
                self.last_stage += "/schema_validation_failed"  # type: ignore[operator]
                parsed = self.fallback_response

        # 6. 최종 fallback 처리
        if parsed is not None:
            return parsed
        else:
            self.last_stage = "fallback_response"
            return self.fallback_response

    def _extract_json_block(self, text: str) -> Union[str, None]:
        try:
            # {} 또는 [] 기준으로 가장 큰 블록 추출
            matches = re.findall(r"(\{[\s\S]*\}|\[[\s\S]*\])", text, re.DOTALL)
            if not matches:
                return None
            # 가장 큰 블록 반환
            return max(matches, key=len)
        except Exception:
            return None

    def _repair_json(self, text: Union[str, None]) -> Union[str, None]:
        if text is None:
            return None
        try:
            text = text.replace("\ufeff", "")  # BOM 제거
            # key가 작은따옴표로 감싸진 경우 큰따옴표로 변환
            text = re.sub(r"'(\w+)'\s*:", r'"\1":', text)
            # value가 작은따옴표로 감싸진 경우 큰따옴표로 변환
            text = re.sub(r":\s*'([^']*)'", r': "\1"', text)
            return text
        except Exception:
            return text

    def _strict_parse(
        self, text: Union[str, None]
    ) -> Union[dict[str, Any], list[Any], None]:
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

    def _lenient_parse(
        self, text: Union[str, None]
    ) -> Union[dict[str, Any], list[Any], None]:
        if not text or json5 is None:
            return None
        try:
            return json5.loads(text)  # type: ignore[union-attr]
        except Exception:
            return None
