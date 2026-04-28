import os


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "passio-python-api")
    DEBUG = _to_bool(os.getenv("FASTAPI_DEBUG"), default=False)

    # RAG
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://100.79.44.109:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-e4b:latest")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
    OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    OLLAMA_DISABLE_THINK = _to_bool(os.getenv("OLLAMA_DISABLE_THINK"), default=True)
    OLLAMA_REWRITE_NUM_PREDICT = int(os.getenv("OLLAMA_REWRITE_NUM_PREDICT", "128"))
    # 기본 off: 엔진은 품질 우선(처음 설계에 가깝게). 속도 프로파일만 쓰려면 RAG_ALWAYS_FAST=1.
    RAG_ALWAYS_FAST = _to_bool(os.getenv("RAG_ALWAYS_FAST"), default=False)
    # 해설 JSON 생성 상한. RAG_ALWAYS_FAST=1이면 기본 6144, 아니면 8192(명시 env 우선).
    if "OLLAMA_SOLVE_NUM_PREDICT" in os.environ:
        OLLAMA_SOLVE_NUM_PREDICT = int(os.environ["OLLAMA_SOLVE_NUM_PREDICT"])
    elif RAG_ALWAYS_FAST:
        OLLAMA_SOLVE_NUM_PREDICT = 6144
    else:
        OLLAMA_SOLVE_NUM_PREDICT = 8192
    OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
    OLLAMA_RETRY_DELAY_SECONDS = float(os.getenv("OLLAMA_RETRY_DELAY_SECONDS", "1.5"))
    RAG_RETRIEVAL_K = int(os.getenv("RAG_RETRIEVAL_K", "6"))
    # 동시 /api/v1/rag/solve 처리 상한. RAG_ALWAYS_FAST일 때 기본 4.
    if "RAG_SOLVE_MAX_PARALLEL" in os.environ:
        RAG_SOLVE_MAX_PARALLEL = max(1, int(os.environ["RAG_SOLVE_MAX_PARALLEL"]))
    else:
        RAG_SOLVE_MAX_PARALLEL = 1
    # 표→서술 사전 변환 전용 생성 토큰 상한 (짧게 두면 속도↑, 품질↓ 가능)
    RAG_TABLE_FIX_NUM_PREDICT = int(os.getenv("RAG_TABLE_FIX_NUM_PREDICT", "2048"))
    RAG_CONTEXT_CHAR_LIMIT = int(os.getenv("RAG_CONTEXT_CHAR_LIMIT", "12000"))
    CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "/home/ubuntu/passio/python_api/chroma_db")
    PDF_PATH = os.getenv("PDF_PATH", "/data/네트워크관리사.pdf")
    MD_PATH = os.getenv("MD_PATH", "/data/theory_only.md")
    CERT_NAME = os.getenv("CERT_NAME", "네트워크 관리사 2급")


settings = Settings()
