from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExamItem(BaseModel):
    """
    단일 시험 문제 항목 (POST /api/v1/rag/solve 요청의 items 원소)
    - q: 문제 본문
    - opts: 보기 (예: '1) TCP, 2) UDP, 3) IP, 4) ICMP')
    - wrong: 오답 선택지
    - ans: 정답 선택지
    """
    q: str = Field(..., description="문제 본문")
    opts: str = Field(..., description="보기 (예: '1) TCP, 2) UDP, 3) IP, 4) ICMP')")
    wrong: str = Field(..., description="오답 선택지")
    ans: str = Field(..., description="정답 선택지")

    @classmethod
    def _is_invalid(cls, v):
        if v is None:
            return True
        if isinstance(v, float) and (v != v):  # NaN check
            return True
        if isinstance(v, str) and (v.strip() == '' or v.strip().lower() == 'nan'):
            return True
        return False

    @classmethod
    def _raise_if_invalid(cls, v, field):
        if cls._is_invalid(v):
            raise ValueError(f"{field} 필드에 빈 값/NaN/None 불가")
        return v

    @classmethod
    def _opts_check(cls, v):
        if cls._is_invalid(v):
            raise ValueError("opts 필드에 빈 값/NaN/None 불가")
        # 허용: str 타입(쉼표로 구분된 4개 보기)
        opts_list = [o.strip() for o in v.split(',')]
        if len(opts_list) != 4 or any(cls._is_invalid(o) for o in opts_list):
            raise ValueError("opts는 쉼표로 구분된 4개 보기여야 하며 빈 값/NaN/None 불가")
        return v

    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @classmethod
    def _validate(cls, v, field):
        v = cls._strip(v)
        return cls._raise_if_invalid(v, field)

    @classmethod
    def _validate_opts(cls, v):
        v = cls._strip(v)
        return cls._opts_check(v)

    # Pydantic validators
    from pydantic import validator
    @validator('q')
    def validate_q(cls, v):
        return cls._validate(v, 'q')

    @validator('ans')
    def validate_ans(cls, v):
        return cls._validate(v, 'ans')

    @validator('wrong')
    def validate_wrong(cls, v):
        return cls._validate(v, 'wrong')

    @validator('opts')
    def validate_opts(cls, v):
        return cls._validate_opts(v)
    search_query: Optional[str] = Field(None, description="온톨로지 분석 기반 확장 검색 쿼리(선택)")
    user_message: Optional[str] = Field(None, description="사용자 추가 요청/해설 지시사항(선택)")
    ontology_subject: Optional[str] = Field(None, description="온톨로지 분류 subject(선택)")
    ontology_chapter: Optional[str] = Field(None, description="온톨로지 분류 chapter(선택)")
    ontology_concept: Optional[str] = Field(None, description="온톨로지 분류 concept(선택)")
    ontology_coordinates: Optional[List[Dict[str, str]]] = Field(
        None, description="온톨로지 복수 분류 좌표 리스트(선택)"
    )


class SolveRequest(BaseModel):
    """
    POST /api/v1/rag/solve 요청 바디
    - items: 문제 리스트 (최소 1, 최대 50)
    - rebuild_db: True면 벡터 DB를 강제 재빌드
    """
    items: List[ExamItem] = Field(..., min_length=1, max_length=50, description="문제 리스트 (최소 1, 최대 50)")
    rebuild_db: bool = Field(False, description="True면 벡터 DB를 강제 재빌드")


class EvidenceItem(BaseModel):
    """
    근거(증거) 문서 항목
    - id: 근거 문서 ID
    - text: 근거 본문
    """
    id: int = Field(..., description="근거 문서 ID")
    text: str = Field(..., description="근거 본문")


class SolveResult(BaseModel):
    """
    단일 문제에 대한 RAG 해설 결과
    - report: 해설/분석 결과(JSON)
    - evidence: 근거 문서 리스트
    """
    report: Dict[str, Any] = Field(..., description="해설/분석 결과(JSON)")
    evidence: List[EvidenceItem] = Field(..., description="근거 문서 리스트")


class SolveResponse(BaseModel):
    """
    POST /api/v1/rag/solve 응답 바디
    - ok: 처리 성공 여부
    - total: 전체 문제 수
    - results: 각 문제별 해설 결과 리스트
    """
    ok: bool = Field(..., description="처리 성공 여부")
    total: int = Field(..., description="전체 문제 수")
    results: List[SolveResult] = Field(..., description="각 문제별 해설 결과 리스트")
