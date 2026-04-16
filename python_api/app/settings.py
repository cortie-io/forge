import os


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "sikdorak-python-api")
    DEBUG = _to_bool(os.getenv("FASTAPI_DEBUG"), default=False)

    # RAG
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://100.79.44.109:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:latest")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3:latest")
    CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "/data/chroma_db")
    PDF_PATH = os.getenv("PDF_PATH", "/data/네트워크관리사-압축됨.pdf")
    MD_PATH = os.getenv("MD_PATH", "/data/theory_only.md")


settings = Settings()
