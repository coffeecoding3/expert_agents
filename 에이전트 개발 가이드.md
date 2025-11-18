# 에이전트 개발 가이드

## 개요

이 문서는 새로운 에이전트를 개발하기 위한 표준화된 가이드입니다. 모든 에이전트는 동일한 인터페이스를 따르며, 쉽게 확장 가능한 구조로 설계되었습니다.

## 아키텍처 개요

### 표준화된 구조
```
src/orchestration/
├── common/
│   └── agent_interface.py          # 표준 인터페이스 정의
├── caia/
│   ├── caia_orchestrator.py        # CAIA 오케스트레이터
│   └── caia_response_handler.py    # CAIA 응답 처리기
├── search/
│   └── search_orchestrator.py      # SearchAgent 오케스트레이터
├── discussion/
│   └── discussion_orchestrator.py  # DiscussionAgent 오케스트레이터
└── examples/
    └── simple_agent_example.py     # 새로운 에이전트 개발 예시
```

## 새로운 에이전트 개발 단계

### 1. 에이전트 상태 정의

```python
from typing import Any, Dict, List
from typing_extensions import TypedDict

class MyAgentState(TypedDict):
    """내 에이전트 상태"""
    # 기본 상태 (CAIAAgentState에서 상속)
    user_query: str
    messages: List[Any]
    agent_id: int
    user_id: int
    session_id: str
    actual_user_id: str
    user_context: Dict[str, Any]
    intent: str
    
    # 에이전트 전용 상태
    my_custom_field: str
    my_result: str
    completed: bool
```

### 2. 에이전트 오케스트레이터 구현

```python
from langgraph.graph import END, StateGraph
from src.orchestration.common.agent_interface import BaseAgentOrchestrator

class MyAgentOrchestrator(BaseAgentOrchestrator):
    """내 에이전트 오케스트레이터"""
    
    def __init__(self):
        self.workflow = self.build_workflow()
    
    def build_workflow(self) -> StateGraph:
        """워크플로우 구성"""
        workflow = StateGraph(MyAgentState)
        
        # 노드 정의
        workflow.add_node("step1", self.node_step1)
        workflow.add_node("step2", self.node_step2)
        
        # 엣지 정의
        workflow.set_entry_point("step1")
        workflow.add_edge("step1", "step2")
        workflow.add_edge("step2", END)
        
        return workflow.compile()
    
    async def node_step1(self, state: MyAgentState) -> Dict[str, Any]:
        """첫 번째 단계"""
        return {"processed": True}
    
    async def node_step2(self, state: MyAgentState) -> Dict[str, Any]:
        """두 번째 단계"""
        return {"result": "완료", "completed": True}
    
    async def run(self, state: CAIAAgentState) -> Dict[str, Any]:
        """에이전트 실행"""
        # 상태 변환 및 워크플로우 실행
        my_state = {**state, "my_custom_field": "", "my_result": "", "completed": False}
        result = await self.workflow.ainvoke(my_state)
        return result
    
    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보"""
        return {
            "name": "MyAgent",
            "description": "내 에이전트 설명",
            "capabilities": ["기능1", "기능2"],
            "supported_intents": ["my_intent"],
        }
    
    def get_supported_intents(self) -> List[str]:
        """지원하는 의도"""
        return ["my_intent"]
```

### 3. 응답 처리기 구현

```python
from src.orchestration.common.agent_interface import AgentResponseHandler

class MyAgentResponseHandler(AgentResponseHandler):
    """내 에이전트 응답 처리기"""
    
    def __init__(self, logger=None):
        self.logger = logger
        self.handled_nodes = ["step1", "step2"]
    
    async def handle_response(
        self, 
        node_name: str, 
        node_output: Any
    ) -> AsyncGenerator[str, None]:
        """응답 처리"""
        from src.schemas.sse_response import SSEResponse
        
        if node_name == "step2":
            # 최종 결과만 스트리밍
            result = node_output.get("result", "") if isinstance(node_output, dict) else str(node_output)
            
            if result:
                for char in result:
                    yield await SSEResponse.create_llm(token=char, done=False).send()
                    await asyncio.sleep(0.01)
                
                yield await SSEResponse.create_llm(
                    token=result,
                    done=True,
                    message_res={
                        "content": result,
                        "role": "assistant",
                        "links": [],
                        "images": [],
                    },
                ).send()
        else:
            # 내부 노드는 응답하지 않음
            self.logger.info(f"Skipping internal node: {node_name}")
    
    def get_handled_nodes(self) -> List[str]:
        """처리 가능한 노드"""
        return self.handled_nodes
```

### 4. 에이전트 등록

```python
from src.apps.api.routers.chat.workflow_manager_v2 import WorkflowManagerFactory

def register_my_agent():
    """내 에이전트 등록"""
    # 워크플로우 매니저 가져오기
    workflow_manager = WorkflowManagerFactory.create_standard_manager()
    
    # 에이전트 생성
    my_orchestrator = MyAgentOrchestrator()
    my_response_handler = MyAgentResponseHandler()
    
    # 등록
    workflow_manager.register_agent(
        agent_code="my_agent",
        orchestrator=my_orchestrator,
        response_handler=my_response_handler
    )
    
    print("내 에이전트 등록 완료!")
```

## 표준 인터페이스

### BaseAgentOrchestrator
- `run(state)`: 에이전트 실행
- `get_agent_info()`: 에이전트 정보 반환
- `get_supported_intents()`: 지원하는 의도 목록

### AgentResponseHandler
- `handle_response(node_name, node_output)`: 응답 처리
- `get_handled_nodes()`: 처리 가능한 노드 목록

## 장점

### 1. 표준화
- 모든 에이전트가 동일한 인터페이스 사용
- 일관된 개발 패턴

### 2. 확장성
- 새로운 에이전트 추가가 간단
- 기존 코드 수정 없이 확장 가능

### 3. 유지보수성
- 각 에이전트가 독립적으로 동작
- 모듈화된 구조

### 4. 테스트 용이성
- 각 컴포넌트를 독립적으로 테스트 가능
- 표준화된 테스트 패턴

## 예시

완전한 예시는 `src/orchestration/examples/simple_agent_example.py`를 참고

## 주의사항

1. **상태 변환**: CAIAAgentState를 에이전트별 상태로 변환해야 함
2. **에러 처리**: 각 노드에서 적절한 에러 처리 필요
3. **로깅**: 일관된 로깅 패턴 사용
4. **리소스 관리**: 메모리 및 연결 리소스 적절히 관리

## 지원

새로운 에이전트 개발 시 문제가 있으면 기존 에이전트들을 참고
