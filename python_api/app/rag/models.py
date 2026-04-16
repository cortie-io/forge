from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExamItem(BaseModel):
    """단일 시험 문제 (오답 분석 요청 단위)"""
    q: str = Field(description="문제 본문")
    opts: str = Field(description="보기 (예: '1) TCP, 2) UDP, 3) IP, 4) ICMP')")
    wrong: str = Field(description="오답 선택지")
    ans: str = Field(description="정답 선택지")


class SolveRequest(BaseModel):
    """POST /api/v1/rag/solve 요청 바디"""
    items: List[ExamItem] = Field(min_length=1, max_length=50)
    rebuild_db: bool = Field(default=False, description="True이면 벡터 DB를 강제 재빌드합니다")


class EvidenceItem(BaseModel):
    id: int
    text: str


class SolveResult(BaseModel):
    report: Dict[str, Any]
    evidence: List[EvidenceItem]


class SolveResponse(BaseModel):
    """POST /api/v1/rag/solve 응답 바디"""
    ok: bool
    total: int
    results: List[SolveResult]
