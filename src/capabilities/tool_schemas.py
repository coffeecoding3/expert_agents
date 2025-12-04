"""
MCP Tool Schemas
MCP 도구들의 스키마 정의를 관리 (동적 스키마 지원)
"""

from typing import Any, Dict


class ToolSchemaManager:
    """도구 스키마 관리자"""

    @staticmethod
    def get_tool_schema(tool_name: str) -> Dict[str, Any]:
        """도구별 스키마 정의 반환 (동적 스키마 지원)"""
        # 알려진 도구들의 스키마 (필요시에만 정의)
        known_schemas = {
            "retrieve_coporate_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "system_codes": {"type": "array", "items": {"type": "string"}},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query", "system_codes", "top_k"]
            },
            "retrieve_personal_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            },
            "get_events": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "start_date_time": {"type": "string"},
                    "end_date_time": {"type": "string"},
                    "date": {"type": "string"}
                },
                "required": []
            },
            "get_mails": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": []
            },
            "send_mail": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["to", "subject", "body"]
            },
            "get_employee_infos_from_human_question": {
                "type": "object",
                "properties": {
                    "human_question": {"type": "string"}
                },
                "required": ["human_question"]
            },
            "get_olap_search_data": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "cube_name": {"type": "string"}
                },
                "required": ["query", "cube_name"]
            },
            "retrieve_scm_knowledge": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            },
            "get_web_search_data": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
        
        # 알려진 스키마가 있으면 반환, 없으면 기본 스키마 반환
        return known_schemas.get(tool_name, {
            "type": "object",
            "properties": {},
            "required": []
        })

    @staticmethod
    def get_all_tool_names() -> list[str]:
        """모든 도구 이름 목록 반환 (동적 도구 지원)"""
        # 알려진 도구들만 반환 (실제로는 외부 서버에서 동적으로 가져와야 함)
        return [
            "retrieve_coporate_knowledge",
            "retrieve_personal_knowledge", 
            "get_events",
            "get_mails",
            "send_mail",
            "get_employee_infos_from_human_question",
            "get_olap_search_data",
            "retrieve_scm_knowledge",
            "get_web_search_data",
        ]
