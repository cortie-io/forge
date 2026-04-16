from fastapi import FastAPI, HTTPException

from .rag.engine import solve_items
from .rag.models import SolveRequest, SolveResponse
from .schemas import HealthResponse

app = FastAPI(title="sikdorak-python-api", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="sikdorak-python-api")


@app.post("/api/v1/rag/solve", response_model=SolveResponse)
def rag_solve(payload: SolveRequest) -> SolveResponse:
    """
    시험 문제 목록을 받아 RAG 기반 해설 JSON을 반환합니다.

    요청 예시:
    {
      "items": [
        {
          "q": "리눅스에서 파일을 이동할 때 사용하는 명령어는?",
          "opts": "1) cp, 2) mv, 3) rm, 4) grep",
          "wrong": "1) cp",
          "ans": "2) mv"
        }
      ],
      "rebuild_db": false
    }
    """
    try:
        results = solve_items(payload.items, force_rebuild=payload.rebuild_db)
        return SolveResponse(ok=True, total=len(results), results=results)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
