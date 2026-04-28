from celery import Celery
from app.rag.engine import solve_items
from app.rag.models import ExamItem
import os

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    "rag_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND
)

@celery_app.task
def run_rag_job(job_id, exam_item_dict, rebuild_db):
    exam_item = ExamItem(**exam_item_dict)
    solve_items([exam_item], force_rebuild=rebuild_db)
    # TODO: DB에 결과 저장, 상태 갱신 등 추가
