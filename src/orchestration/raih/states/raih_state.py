import operator
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class RAIHAgentState(TypedDict):
    """
    에이전트의 상태를 나타냅니다.

    Attributes:
        user_query: 사용자 질의
        messages: 현재 대화의 메시지 기록. (입력/출력)
        memory: 메모리에서 가져온 과거 대화 기록.
        intent: 쿼리 의도 분류 결과.
        memory_candidate: 메모리에서 추출한 메모리 후보.
        search_agent_output: 검색/도구 실행 결과.
        next_node: 다음에 실행할 노드.
        user_context: 세분화된 사용자 컨텍스트
            - recent_messages: 최근 대화 k개 (단기기억)
            - session_summary: 해당 세션 요약 (단기기억)
            - (todo)semantic_memories: Semantic 메모리 (장기기억, 개인정보 포함)
            - (todo)episodic_memories: Episodic 메모리 (장기기억, 선택적)
            - (todo)procedural_memories: Procedural 메모리 (장기기억, 선택적)
            - long_term_memories: (장기기억 종합)
            - personal_info: 개인정보 컨텍스트 (인사정보, 경력정보 등)
    """

    user_query: str
    messages: Annotated[Sequence[BaseMessage], operator.add]
    agent_id: Optional[int]
    user_id: Optional[int]
    actual_user_id: Optional[str]
    session_id: Optional[str]
    channel_id: Optional[int]  # 채팅 채널 ID
    user_message_id: Optional[int]  # 사용자 메시지 ID
    assistant_message_id: Optional[int]  # 저장된 AI 응답 메시지 ID
    memory: Optional[List[Dict[str, Any]]] = None
    intent: Optional[str] = None
    memory_candidate: Optional[str] = None
    search_agent_output: Optional[str] = None
    next_node: str
    user_context: Optional[Dict[str, Any]]
