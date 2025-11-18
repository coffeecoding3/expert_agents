# CAIA (Chief AI Advisor) 아키텍처

## 워크플로우 다이어그램

```mermaid
graph TD
    A[사용자 질의] --> B[ChatResponseGeneratorV2]
    B --> C[WorkflowManager]
    B --> D[MessageStorageManager]
    B --> E[MemoryManager]
    
    C --> F[CAIAOrchestrator]
    F --> G[SearchOrchestrator]
    F --> H[DiscussionOrchestrator]
    
    G --> I[SearchPlanningNode]
    G --> J[SearchExecutionNode]
    G --> K[SearchCompressionNode]
    
    H --> L[SetupDiscussionNode]
    H --> M[GetMaterialsNode]
    H --> N[ProceedDiscussionNode]
    H --> O[WrapUpDiscussionNode]
    
    D --> P[Chat Messages DB]
    E --> Q[STM Redis]
    E --> R[LTM MySQL]

    subgraph "메모리 시스템"
        direction TB
        STM[STM<br/>Redis<br/>세션별 대화]
        LTM[LTM<br/>MySQL<br/>장기 기억]
        SEM[Semantic<br/>개념적 지식]
        EPI[Episodic<br/>경험적 기억]
        PRO[Procedural<br/>절차적 지식]
    end

    subgraph "SearchAgent (그래프 구조)"
        direction TB
        SA1[SearchPlanningNode<br/>도구 계획 수립]
        SA2[SearchExecutionNode<br/>도구 실행]
        SA3[SearchCompressionNode<br/>결과 압축]
        SA1 --> SA2
        SA2 --> SA3
    end

    subgraph "DiscussionAgent (그래프 구조)"
        direction TB
        D1[SetupDiscussionNode<br/>토론 설정]
        D2[GetMaterialsNode<br/>자료 수집]
        D3[ProceedDiscussionNode<br/>토론 진행]
        D4[WrapUpDiscussionNode<br/>토론 요약]
        D1 --> D2
        D2 --> D3
        D3 --> D4
    end

    Q -.-> STM
    R -.-> LTM
    LTM -.-> SEM
    LTM -.-> EPI
    LTM -.-> PRO
```

## 아키텍처 특징

### 1. 완전한 그래프 구조
- **SearchAgent**: SearchOrchestrator → SearchPlanningNode → SearchExecutionNode → SearchCompressionNode
- **DiscussionAgent**: DiscussionOrchestrator → SetupDiscussionNode → GetMaterialsNode → ProceedDiscussionNode → WrapUpDiscussionNode
- **각 에이전트가 독립적인 StateGraph로 동작**

### 2. 책임 분리된 컴포넌트
- **ChatResponseGeneratorV2**: 핵심 로직만 담당 (의도 분석, 초기화)
- **WorkflowManager**: 워크플로우 실행 및 SSE 스트리밍
- **MessageStorageManager**: 메시지 저장 로직 분리
- **MemoryManager**: STM/LTM 저장 로직 분리

### 3. 노드별 상세 설명

#### **ChatResponseGeneratorV2**
- 사용자 질의 수신 및 초기화
- 의도 분석 및 에이전트 라우팅
- 매니저들 간의 조율

#### **WorkflowManager**
- 워크플로우 실행 및 관리
- SSE 스트리밍 처리
- 노드별 결과 변환

#### **SearchOrchestrator (완전한 그래프 구조)**
- **SearchPlanningNode**: 검색 계획 수립
- **SearchExecutionNode**: 도구 실행
- **SearchCompressionNode**: 결과 압축

#### **DiscussionOrchestrator (완전한 그래프 구조)**
- **SetupDiscussionNode**: 토론 설정 및 전문가 선정
- **GetMaterialsNode**: 토론 자료 수집
- **ProceedDiscussionNode**: 실시간 토론 시뮬레이션
- **WrapUpDiscussionNode**: 토론 요약 및 WOW Point 도출

#### **MessageStorageManager**
- 토론 발언별 메시지 저장 (caia_discussion_{speaker_name} 형식)
- 일반 응답 메시지 저장
- 데이터베이스 연동

#### **MemoryManager**
- STM 메시지 저장 (Redis)
- LTM 추출 및 저장 (MySQL)
- 토론 스크립트 포함 저장

## 메모리 시스템 구조

### STM (Short-Term Memory)
- **저장소**: Redis
- **용도**: 세션별 대화 기록, 임시 정보
- **수명**: 세션 종료 시 삭제
- **토론 지원**: 발언자별 내용 저장 (speaker1, speaker2, host 등)

### LTM (Long-Term Memory)
- **저장소**: MySQL
- **용도**: 장기 기억, 개인화 정보
- **유형**: 
  - Semantic: 개념적 지식
  - Episodic: 경험적 기억
  - Procedural: 절차적 지식

## 아키텍처 개선 효과

### 1. 확장성
- 새로운 에이전트 추가 시 동일한 패턴 적용 가능
- 각 에이전트가 독립적으로 개발 및 테스트 가능

### 2. 유지보수성
- 각 컴포넌트의 책임이 명확히 분리
- 모듈화된 구조로 디버깅 및 수정 용이

### 3. 테스트 용이성
- 각 노드를 독립적으로 테스트 가능
- 매니저별 단위 테스트 가능

### 4. 성능 최적화
- 병렬 처리 가능한 구조
- 메모리 사용량 최적화

### 5. 일관된 인터페이스
- 모든 에이전트가 동일한 패턴으로 동작
- 새로운 개발자가 이해하기 쉬운 구조

