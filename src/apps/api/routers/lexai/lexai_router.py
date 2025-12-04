"""
LexAI Router

법령 개정 분석 및 사내 규정 변경 조언을 위한 API 엔드포인트
"""

import json
import time
from logging import getLogger
from typing import Any, Dict

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from src.database.connection import get_database_session
from src.database.models import APIKey
from src.database.services import task_service
from src.orchestration.common.workflow_registry import workflow_registry
from src.orchestration.lexai.lexai_response_handler import LexAIResponseHandler
from src.schemas.lexai_schemas import (
    ConsistencyCheckRequest,
    ConsistencyCheckResponse,
    ConsistencyCheckSuggestion,
    LexAIRequest,
    RegulationChangeResponse,
)
from src.apps.api.security.api_key_auth import verify_api_key

logger = getLogger("lexai_router")


async def verify_lexai_api_key(
    x_api_key: Optional[str] = Header(
        None, alias="X-API-Key", description="LexAI API Key"
    ),
    db: Session = Depends(get_database_session),
) -> APIKey:
    """LexAI 전용 API Key 검증 의존성"""
    return await verify_api_key(x_api_key=x_api_key, db=db, agent_code="lexai")


# LexAI 라우터
lexai_router = APIRouter(
    prefix="/lexai/api/v1",
    tags=["LexAI - 법령 개정 분석"],
    responses={
        404: {"description": "에이전트를 찾을 수 없습니다"},
        500: {"description": "서버 내부 오류"},
    },
)


def get_orchestrator(agent_code: str = "lexai"):
    """오케스트레이터를 가져옵니다."""
    orchestrator = workflow_registry.get_orchestrator(agent_code)
    if not orchestrator:
        raise HTTPException(
            status_code=404,
            detail=f"{agent_code} 에이전트를 찾을 수 없습니다.",
        )
    return orchestrator


def get_state_builder(agent_code: str = "lexai"):
    """상태 빌더를 가져옵니다."""
    state_builder = workflow_registry.get_state_builder(agent_code)
    if not state_builder:
        raise HTTPException(
            status_code=404,
            detail=f"{agent_code} 상태 빌더를 찾을 수 없습니다.",
        )
    return state_builder


@lexai_router.post(
    "/analyze",
    response_model=RegulationChangeResponse,
    status_code=status.HTTP_200_OK,
    summary="법령 개정 분석 및 규정 변경 조언",
    description="""
    법령 개정 내용을 분석하여 사내 규정 변경 조언을 생성합니다.
    
    ### 처리 과정
    1. 법령명과 개정 내용을 분석하여 사내 규정 검색 쿼리 생성
    2. 생성된 쿼리로 사내 규정 검색 (corporate_knowledge)
    3. 법령 개정 내용과 사내지식을 기반으로 LLM이 규정 변경 조언 생성
    4. 분석 결과를 데이터베이스에 저장
    5. 생성된 조언을 JSON 형식으로 반환
    
    ### 주의사항
    - 처리 시간이 오래 걸릴 수 있습니다 (최대 300초)
    - `corporate_knowledge`는 사내지식 검색 결과가 있을 때만 포함됩니다
    - `details` 배열이 비어있으면 수정제안이 없다는 의미입니다
    """,
    responses={
        200: {
            "description": "분석 성공",
            "content": {
                "application/json": {
                    "example": {
                        "openapi_log_id": "55",
                        "old_and_new_no": "273603",
                        "details": [
                            {
                                "center": "안전환경센터",
                                "category": "안전",
                                "standard": "안전보건관리규정",
                                "content_no": "4",
                                "before_lgss_content": "N/A",
                                "ai_review": "용접방화포는 「소방시설 설치 및 관리에 관한 법률」 제40조제1항에 따라 성능인증을 받은 것을 사용 규정 추가",
                                "ai_suggestion": "비산방지조치에 성능인증 항목 추가",
                                "suggetsion_accuracy": "80",
                            }
                        ],
                        "corporate_knowledge": {
                            "documents": [
                                {"title": "안전보건관리규정", "content": "..."}
                            ]
                        },
                    }
                }
            },
        },
        401: {
            "description": "인증 실패",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "API Key가 필요합니다. X-API-Key 헤더를 포함해주세요."
                    }
                }
            },
        },
        404: {
            "description": "에이전트를 찾을 수 없습니다",
            "content": {
                "application/json": {
                    "example": {"detail": "lexai 에이전트를 찾을 수 없습니다."}
                }
            },
        },
        500: {
            "description": "서버 내부 오류",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "법령 개정 분석 중 오류가 발생했습니다: [에러 메시지]"
                    }
                }
            },
        },
    },
)
async def analyze_law_revision(
    request: LexAIRequest,
    db: Session = Depends(get_database_session),
    api_key: APIKey = Depends(verify_lexai_api_key),
    orchestrator=Depends(get_orchestrator),
    state_builder=Depends(get_state_builder),
) -> RegulationChangeResponse:
    """
    법령 개정 내용을 분석하여 사내 규정 변경 조언을 생성합니다.

    Args:
        request: 법령 개정 요청 데이터
            - openapi_log_id: OpenAPI 로그 ID
            - old_and_new_no: 개정 전후 번호
            - law_nm: 법령명
            - contents: 법령 개정 내용 목록
        orchestrator: 오케스트레이터
        state_builder: 상태 빌더

    Returns:
        RegulationChangeResponse: 규정 변경 조언 응답
            - openapi_log_id: OpenAPI 로그 ID
            - old_and_new_no: 개정 전후 번호
            - details: 규정 변경 상세 목록
            - corporate_knowledge: 검색된 사내지식 정보 (Optional)
    """
    logger.info(
        f"[LEXAI_ROUTER] 법령 개정 분석 요청: {request.law_nm} (openapi_log_id: {request.openapi_log_id})"
    )

    # 처리 시작 시간
    start_time = time.time()
    task = None

    try:
        # Task 생성
        request_data = request.model_dump()
        task = task_service.create_task(
            db=db,
            openapi_log_id=request.openapi_log_id,
            old_and_new_no=request.old_and_new_no,
            law_nm=request.law_nm,
            request_data=request_data,
            status="processing",
        )

        if not task:
            logger.error("[LEXAI_ROUTER] Task 생성 실패")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="작업 이력 생성에 실패했습니다.",
            )

        # 요청 데이터를 상태로 변환
        contents = [
            {
                "content_no": content.content_no,
                "old_content": content.old_content,
                "new_content": content.new_content,
            }
            for content in request.contents
        ]

        state = state_builder.create_state(
            user_query=request.law_nm,
            messages=[HumanMessage(content=request.law_nm)],
            agent_id=3,  # lexai agent_id (DB에서 조회 필요)
            openapi_log_id=request.openapi_log_id,
            old_and_new_no=request.old_and_new_no,
            law_nm=request.law_nm,
            contents=contents,
        )

        # Response handler 생성
        response_handler = LexAIResponseHandler(logger=logger)

        # 워크플로우 실행 및 결과 수집
        final_state = {}
        async for output in orchestrator.workflow.astream(state):
            for node_name, node_output in output.items():
                # Response handler로 결과 수집
                await response_handler.handle_response(node_name, node_output)
                # 최종 상태 업데이트
                if isinstance(node_output, dict):
                    final_state.update(node_output)

        # 최종 결과 가져오기
        final_result = response_handler.get_final_result()
        advice = final_result.get("advice", {})
        corporate_knowledge = final_result.get("corporate_knowledge")

        # LLM 응답에서 JSON 파싱 시도
        advice_content = advice.get("content", "")
        llm_model = advice.get("model")
        llm_usage = advice.get("usage")

        # JSON 파싱 시도
        try:
            # LLM이 JSON을 반환했다고 가정하고 파싱
            if advice_content.strip().startswith("{"):
                parsed_advice = json.loads(advice_content)
            else:
                # JSON이 아닌 경우 기본 구조 생성
                parsed_advice = {
                    "openapi_log_id": request.openapi_log_id,
                    "old_and_new_no": request.old_and_new_no,
                    "details": [],
                }
                logger.warning(
                    "[LEXAI_ROUTER] LLM 응답이 JSON 형식이 아닙니다. 기본 구조를 사용합니다."
                )
        except json.JSONDecodeError as e:
            logger.error(f"[LEXAI_ROUTER] JSON 파싱 실패: {e}")
            # 파싱 실패 시 기본 구조 반환
            parsed_advice = {
                "openapi_log_id": request.openapi_log_id,
                "old_and_new_no": request.old_and_new_no,
                "details": [],
            }

        # RegulationChangeResponse로 변환 (corporate_knowledge 포함)
        parsed_advice["corporate_knowledge"] = corporate_knowledge
        response = RegulationChangeResponse(**parsed_advice)

        # 처리 시간 계산
        processing_time_ms = int((time.time() - start_time) * 1000)

        # Task 업데이트
        if task:
            task_service.update_task(
                db=db,
                task_id=task.task_id,
                corporate_knowledge=corporate_knowledge,
                advice_content=advice_content,
                advice_parsed=parsed_advice,
                status="completed",
                processing_time_ms=processing_time_ms,
                llm_model=llm_model,
                llm_usage=llm_usage,
            )

        logger.info(
            f"[LEXAI_ROUTER] 법령 개정 분석 완료: {len(response.details)}개 조언 생성 (task_id: {task.task_id if task else 'N/A'})"
        )

        return response

    except HTTPException:
        if task:
            task_service.update_task(
                db=db,
                task_id=task.task_id,
                status="failed",
                error_message="HTTPException 발생",
            )
        raise
    except Exception as e:
        logger.error(f"[LEXAI_ROUTER] 법령 개정 분석 실패: {e}", exc_info=True)

        # Task 업데이트 (실패 상태)
        if task:
            processing_time_ms = int((time.time() - start_time) * 1000)
            task_service.update_task(
                db=db,
                task_id=task.task_id,
                status="failed",
                error_message=str(e),
                processing_time_ms=processing_time_ms,
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"법령 개정 분석 중 오류가 발생했습니다: {str(e)}",
        )


@lexai_router.post(
    "/consistency-check",
    response_model=ConsistencyCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="정합성 체크 조회",
    description="""
    작업 완료된 법령 개정 분석 결과를 조회하여 정합성 체크 결과를 반환합니다.
    
    ### 동작 방식
    1. `law_nm`으로 가장 최근 완료된 분석 작업을 조회
    2. `advice_parsed`에서 `standard`가 일치하는 detail을 찾음
    3. 찾은 detail을 `ConsistencyCheckResponse` 형식으로 변환
       - `check_rst`: 제안이 있으면 "일부 수정", 없으면 "완료"
       - `suggetsion_accuracy`: 매칭된 detail들의 정확도 평균
       - `ai_suggestions`: `content_no`를 `line`으로, `ai_suggestion`을 `suggestion`으로 매핑
    
    ### 주의사항
    - 해당 법령명으로 완료된 분석 작업이 없으면 404 에러가 발생합니다
    - 해당 규정명에 대한 분석 결과가 없으면 404 에러가 발생합니다
    - `ai_suggestions`가 비어있으면 수정제안이 없다는 의미입니다
    """,
    responses={
        200: {
            "description": "조회 성공",
            "content": {
                "application/json": {
                    "example": {
                        "law_nm": "산업안전보건기준에 관한 규칙",
                        "standard": "안전보건관리규정",
                        "check_rst": "일부 수정",
                        "suggetsion_accuracy": "88",
                        "ai_suggestions": [
                            {
                                "line": "4",
                                "suggestion": "비산방지조치에 성능인증 항목 추가",
                            },
                            {
                                "line": "8",
                                "suggestion": "'운반기계등'을 '굴착기계등'으로 수정",
                            },
                        ],
                    }
                }
            },
        },
        401: {
            "description": "인증 실패",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "API Key가 필요합니다. X-API-Key 헤더를 포함해주세요."
                    }
                }
            },
        },
        404: {
            "description": "분석 결과를 찾을 수 없습니다",
            "content": {
                "application/json": {
                    "examples": {
                        "law_not_found": {
                            "summary": "법령명으로 완료된 분석 결과 없음",
                            "value": {
                                "detail": "'산업안전보건기준에 관한 규칙'에 대한 완료된 분석 결과를 찾을 수 없습니다."
                            },
                        },
                        "data_not_found": {
                            "summary": "분석 결과 데이터 없음",
                            "value": {"detail": "분석 결과 데이터가 없습니다."},
                        },
                        "standard_not_found": {
                            "summary": "규정명에 대한 분석 결과 없음",
                            "value": {
                                "detail": "'안전보건관리규정' 규정에 대한 분석 결과를 찾을 수 없습니다."
                            },
                        },
                    }
                }
            },
        },
        500: {
            "description": "서버 내부 오류",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "정합성 체크 조회 중 오류가 발생했습니다: [에러 메시지]"
                    }
                }
            },
        },
    },
)
async def get_consistency_check(
    request: ConsistencyCheckRequest,
    db: Session = Depends(get_database_session),
    api_key: APIKey = Depends(verify_lexai_api_key),
) -> ConsistencyCheckResponse:
    """
    법령명과 규정명으로 작업 완료된 분석 결과를 조회하여 정합성 체크 결과를 반환합니다.

    Args:
        request: 정합성 체크 요청 데이터
            - law_nm: 법령명
            - standard: 규정명
        db: 데이터베이스 세션

    Returns:
        ConsistencyCheckResponse: 정합성 체크 결과
            - law_nm: 법령명
            - standard: 규정명
            - check_rst: 체크 결과 ("완료" 또는 "일부 수정")
            - suggetsion_accuracy: 제안 정확도 (0-100)
            - ai_suggestions: AI 제안 사항 목록
    """
    logger.info(
        f"[LEXAI_ROUTER] 정합성 체크 조회 요청: {request.law_nm} - {request.standard}"
    )

    try:
        # law_nm으로 가장 최근 완료된 작업 조회
        task = task_service.get_latest_completed_by_law_nm(db=db, law_nm=request.law_nm)

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{request.law_nm}'에 대한 완료된 분석 결과를 찾을 수 없습니다.",
            )

        if not task.advice_parsed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="분석 결과 데이터가 없습니다.",
            )

        # advice_parsed에서 해당 standard와 일치하는 detail 찾기
        details = task.advice_parsed.get("details", [])
        matching_details = [
            detail for detail in details if detail.get("standard") == request.standard
        ]

        if not matching_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{request.standard}' 규정에 대한 분석 결과를 찾을 수 없습니다.",
            )

        # 첫 번째 매칭되는 detail 사용 (여러 개일 경우 첫 번째)
        detail = matching_details[0]

        # 정확도 계산 (여러 detail이 있으면 평균, 없으면 첫 번째 것 사용)
        accuracies = []
        for d in matching_details:
            accuracy = d.get("suggetsion_accuracy", "0")
            try:
                # 문자열이면 숫자로 변환 시도
                if isinstance(accuracy, str):
                    if accuracy.isdigit():
                        accuracies.append(int(accuracy))
                elif isinstance(accuracy, (int, float)):
                    accuracies.append(int(accuracy))
            except (ValueError, TypeError):
                continue

        avg_accuracy = (
            str(int(sum(accuracies) / len(accuracies))) if accuracies else "0"
        )

        # check_rst 결정 (제안이 있으면 "일부 수정", 없으면 "완료")
        has_suggestions = any(
            d.get("ai_suggestion", "").strip()
            and d.get("ai_suggestion", "").strip().upper() != "N/A"
            for d in matching_details
        )
        check_rst = "일부 수정" if has_suggestions else "완료"

        # ai_suggestions 생성 (content_no를 line으로 사용)
        ai_suggestions = []
        for d in matching_details:
            suggestion = d.get("ai_suggestion", "").strip()
            if suggestion and suggestion.upper() != "N/A":
                ai_suggestions.append(
                    ConsistencyCheckSuggestion(
                        line=d.get("content_no", ""),
                        suggestion=suggestion,
                    )
                )

        # 응답 생성
        response = ConsistencyCheckResponse(
            law_nm=request.law_nm,
            standard=request.standard,
            check_rst=check_rst,
            suggetsion_accuracy=avg_accuracy,
            ai_suggestions=ai_suggestions,
        )

        logger.info(
            f"[LEXAI_ROUTER] 정합성 체크 조회 완료: {request.law_nm} - {request.standard} "
            f"(제안 {len(ai_suggestions)}개)"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LEXAI_ROUTER] 정합성 체크 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"정합성 체크 조회 중 오류가 발생했습니다: {str(e)}",
        )
