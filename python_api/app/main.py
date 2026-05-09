
"""
sikdorak-python-api (FastAPI)
─────────────────────────────
• 동기 RAG 엔드포인트: Ollama + Chroma 기반 `solve_items()` (CPU/IO 집중)
• asyncpg 기반 관리/조회 API 일부
• 운영: PM2 `rag-api`가 uvicorn으로 이 앱을 구동

Express(forge-node)와의 관계:
• 웹 UX용 “job 큐”는 Node가 담당, 실제 추론은 Node가 이 서비스의 `/api/v1/rag/solve`를 호출

상세 문서: 저장소 루트 `docs/SYSTEM-ARCHITECTURE.md`
"""

import json
import os
import asyncio
import re
import threading
import secrets
import random
import urllib.error
import urllib.request
from types import SimpleNamespace
from contextlib import asynccontextmanager
import time
from pathlib import Path
import asyncpg
import bcrypt
from datetime import datetime
from typing import Any, Callable, Optional, Dict, List

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import BaseModel, Field
from starlette.responses import Response

from .rag.engine import solve_items
from .rag.chroma_store import get_langchain_chroma
from .rag.conversation_context import (
    augment_payload_for_ontology_followup,
    format_history_for_leg_prompt,
    history_suggests_problem_explain,
)
from .rag.concept_explain_leg import (
    build_concept_explain_leg_prompt,
    format_concept_explain_leg_for_chat,
)
from .rag.etc_reply import build_etc_reply as build_etc_reply_external
from .rag.mcq_payload import format_leg_report_for_chat, try_build_exam_item_for_explain_problem
from .rag.ontology_engine import ForgeOntologyEngine
from .rag.models import EvidenceItem, ExamItem, SolveRequest, SolveResponse
from .rag.problem_explain_leg import (
    extract_problem_explain_leg_json,
    has_nonempty_problem_explain_leg_refined,
    is_problem_explain_leg_audit_consistent,
    is_problem_explain_leg_body_valid,
    normalize_problem_explain_leg_report,
    repair_problem_explain_leg_audit,
)
from .schemas import HealthResponse
from .settings import settings

# solve 경로는 Chroma를 주로 읽기만 하지만, SQLite 백엔드에서 동시 접근이 겹치면
# busy/timeout이 날 수 있어 완전 무제한 병렬은 피하고 제한적 병렬만 허용합니다.
# (과거 전역 Lock은 모든 요청을 1개로 직렬화 → 대기열 지연 폭증)
_rag_solve_semaphore = threading.BoundedSemaphore(settings.RAG_SOLVE_MAX_PARALLEL)
_forge_ontology_engine = ForgeOntologyEngine(cert_name=settings.CERT_NAME)

# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────

# database 주소 환경변수에서 읽기 (예: postgresql://user:password@host:port/dbname)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sikdorak_app:sikdorak_password@127.0.0.1:5432/sikdorak" # 기본값
)
API_LOG_JSONL_PATH = Path(
    os.getenv("API_LOG_JSONL_PATH", "/tmp/sikdorak_api_request_logs.jsonl")
).expanduser().resolve()


from .utils import mask_sensitive


QUESTION_SEARCH_KEYWORDS = (
    "유사문제",
    "비슷한 문제",
    "관련 문제",
    "문제 몇 개",
    "기출문제",
    "연습문제",
    "문제 찾아",
    "문제 추천",
    "문제 줘",
    "similar question",
    "similar questions",
    "practice problem",
    "practice problems",
    "find questions",
    "세트",
    "문제 세트",
    "set of",
)

MOCK_EXAM_CONTEXT_START = "[FORGE_MOCK_EXAM_CONTEXT]"
MOCK_EXAM_CONTEXT_END = "[/FORGE_MOCK_EXAM_CONTEXT]"


def _strip_mock_exam_context_block(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    pattern = re.compile(
        re.escape(MOCK_EXAM_CONTEXT_START) + r"\s*.*?\s*" + re.escape(MOCK_EXAM_CONTEXT_END),
        re.DOTALL,
    )
    cleaned = pattern.sub("", raw)
    return cleaned.strip()


async def log_api_request_jsonl(
    *,
    endpoint: str,
    method: str,
    user_id: Any = None,
    request_payload: Any = None,
    response_payload: Any = None,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    response_time_ms: Optional[float] = None,
) -> None:
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "endpoint": endpoint,
        "method": method,
        "user_id": user_id,
        "request_payload": mask_sensitive(request_payload),
        "response_payload": mask_sensitive(response_payload),
        "status_code": status_code,
        "error_message": error_message,
        "response_time_ms": int(response_time_ms) if response_time_ms is not None else None,
    }
    try:
        API_LOG_JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with API_LOG_JSONL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _dispatch_api_logs(
    *,
    endpoint: str,
    method: str,
    user_id: Any = None,
    request_payload: Any = None,
    response_payload: Any = None,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    response_time_ms: Optional[float] = None,
) -> None:
    asyncio.create_task(log_api_request_jsonl(
        endpoint=endpoint,
        method=method,
        user_id=user_id,
        request_payload=request_payload,
        response_payload=response_payload,
        status_code=status_code,
        error_message=error_message,
        response_time_ms=response_time_ms,
    ))


def _format_analysis_coords(analysis: Any) -> str:
    coords = getattr(analysis, "coordinates", None) or []
    parts: List[str] = []
    for coord in coords:
        if hasattr(coord, "subject"):
            subject = str(getattr(coord, "subject", "") or "").strip()
            chapter = str(getattr(coord, "chapter", "") or "").strip()
            concept = str(getattr(coord, "concept", "") or "").strip()
        elif isinstance(coord, dict):
            subject = str(coord.get("subject", "") or "").strip()
            chapter = str(coord.get("chapter", "") or "").strip()
            concept = str(coord.get("concept", "") or "").strip()
        else:
            continue
        label = " > ".join(x for x in [subject, chapter, concept] if x)
        if label:
            parts.append(label)
    return ", ".join(parts[:4])


def _normalize_lookup_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _extract_requested_question_count(payload: str) -> int:
    match = re.search(r"(\d{1,2})\s*(개|문제)", str(payload or ""))
    if match:
        try:
            return max(1, min(int(match.group(1)), 10))
        except ValueError:
            pass
    return 3


def _has_explicit_question_search_request(payload: str) -> bool:
    text = _normalize_lookup_text(payload)
    compact = text.replace(" ", "")
    if any(
        _normalize_lookup_text(keyword) in text
        or _normalize_lookup_text(keyword).replace(" ", "") in compact
        for keyword in QUESTION_SEARCH_KEYWORDS
    ):
        return True
    bank_lookup_intent = (
        "문제은행" in text
        and any(keyword in text for keyword in ("관련", "유사", "찾", "뽑", "추천", "기출", "연습"))
    )
    if bank_lookup_intent:
        return True
    return any(keyword in text for keyword in ("기출", "유형문제", "문제 더", "추가 문제", "더 찾아", "추천 문제"))


def _wants_question_search(payload: str, analysis: Any) -> bool:
    text = _normalize_lookup_text(payload)
    explicit_search = _has_explicit_question_search_request(payload)
    intent = str(getattr(analysis, "intent", "") or "")
    sequence = _analysis_intent_sequence(analysis) if analysis else []
    if intent == "QUESTION_SEARCH":
        return True
    if "QUESTION_SEARCH" in sequence:
        # For pure problem explanation, require explicit search wording.
        if intent == "EXPLAIN_PROBLEM" and not explicit_search:
            return False
        return True
    if intent not in {"FOLLOWUP", "CONCEPT_EXPLAIN", "QUIZ_REQUEST", "EXPLAIN_PROBLEM"}:
        return False
    if explicit_search:
        return True
    count = _extract_requested_question_count(payload)
    if count >= 5 and ("문제" in text or "question" in text):
        return True
    return False


def _payload_has_question_block(payload: str) -> bool:
    text = str(payload or "")
    if "[문제]" in text and "[보기]" in text:
        return True
    numbered_style = all(
        re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        for pattern in (
            r"^\s*1\s*[\)\.]",
            r"^\s*2\s*[\)\.]",
            r"^\s*3\s*[\)\.]",
            r"^\s*4\s*[\)\.]",
        )
    )
    circled_style = all(mark in text for mark in ("①", "②", "③", "④"))
    return numbered_style or circled_style


def _analysis_intent_sequence(analysis: Any) -> List[str]:
    allowed = {
        "QUIZ_REQUEST",
        "QUESTION_SEARCH",
        "CONCEPT_EXPLAIN",
        "EXPLAIN_PROBLEM",
        "FOLLOWUP",
        "SYSTEM_CONTROL",
        "MOCK_EXAM_ANALYZE",
        "ETC",
    }
    seq: List[str] = []
    raw_seq = getattr(analysis, "intent_sequence", None)
    if isinstance(raw_seq, list):
        for item in raw_seq:
            tag = str(item or "").strip()
            if tag in allowed and tag not in seq:
                seq.append(tag)
    intent = str(getattr(analysis, "intent", "") or "").strip()
    if intent in allowed and intent not in seq:
        seq.insert(0, intent)
    return seq


def _wants_mock_exam_analysis(payload_raw: str, history: List[Dict[str, str]], analysis: Any | None = None) -> bool:
    context = _extract_mock_exam_context(payload_raw, history)
    if not context:
        return False
    user_text_raw = _strip_mock_exam_context_block(payload_raw)

    text = _normalize_lookup_text(user_text_raw)
    compact = text.replace(" ", "")
    numbers = _extract_mock_question_numbers(user_text_raw)

    excludes_mock_context = (
        any(term in text for term in ("상관없이", "무관하게", "무관", "제외", "빼고", "말고"))
        and any(term in text for term in ("모의고사", "mock"))
    )

    if excludes_mock_context and not numbers:
        return False

    seq = _analysis_intent_sequence(analysis) if analysis is not None else []
    if "MOCK_EXAM_ANALYZE" in seq:
        return True

    has_explicit_mock_term = any(
        keyword in text for keyword in ("모의고사", "이번 시험", "이 시험", "푼 모의고사", "mock exam", "mock")
    )
    has_mock_stats_intent = any(
        keyword in text
        for keyword in (
            "오답",
            "틀린",
            "정답률",
            "취약",
            "빈출",
            "중복",
            "패턴",
            "점수",
            "과목별",
            "분석",
            "학습",
            "우선순위",
        )
    )
    has_numbered_followup = bool(numbers) and any(
        keyword in text for keyword in ("해설", "풀이", "설명", "복기", "왜", "정답", "오답")
    )

    # If the user clearly asks for question-bank retrieval, avoid forcing mock-analysis.
    wants_question_bank = (
        _payload_wants_question_search(user_text_raw)
        or "문제은행" in text
        or "question bank" in text
        or "questionbank" in compact
    )
    if wants_question_bank and not (has_explicit_mock_term or has_numbered_followup):
        return False

    return has_explicit_mock_term or has_mock_stats_intent or has_numbered_followup


def _extract_question_reference_index(payload: str) -> int | None:
    text = str(payload or "")
    for pattern in (r"(?:^|\s)(\d{1,2})번", r"#(\d{1,2})", r"(?:number|no\.?|item)\s*(\d{1,2})"):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_recommended_questions_from_history(history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r"\[추천 문제\s+(?P<idx>\d+)\]\s*\n\[문제\]\n(?P<question>.*?)\n\n\[보기\]\n(?P<options>.*?)(?:\n\n\[정답\]\n(?P<answer>.*?))?(?=\n\[추천 문제\s+\d+\]|\Z)",
        re.DOTALL,
    )
    for msg in reversed(history or []):
        if str(msg.get("role", "")) != "assistant":
            continue
        content = str(msg.get("content", "") or "")
        matches = list(pattern.finditer(content))
        if not matches:
            continue
        out: List[Dict[str, Any]] = []
        for match in matches:
            options = []
            for line in str(match.group("options") or "").splitlines():
                cleaned = re.sub(r"^\s*\d+\)\s*", "", line).strip()
                if cleaned:
                    options.append(cleaned)
            if len(options) != 4:
                continue
            out.append(
                {
                    "index": int(match.group("idx")),
                    "question": str(match.group("question") or "").strip(),
                    "options": options,
                    "answer_choice": str(match.group("answer") or "").strip(),
                }
            )
        if out:
            return out
    return []


def _resolve_referenced_question_payload(payload: str, history: List[Dict[str, str]]) -> str:
    reference_index = _extract_question_reference_index(payload)
    if not reference_index:
        return payload
    recommended = _extract_recommended_questions_from_history(history)
    target = next((item for item in recommended if int(item.get("index", 0)) == reference_index), None)
    if not target:
        return payload
    option_lines = "\n".join(
        f"{idx + 1}) {option}" for idx, option in enumerate(target.get("options") or [])
    )
    blocks = [
        f"[사용자 메시지]\n{payload.strip()}",
        f"[문제]\n{str(target.get('question', '') or '').strip()}",
        f"[보기]\n{option_lines}",
    ]
    answer_choice = str(target.get("answer_choice", "") or "").strip()
    if answer_choice:
        blocks.append(f"[정답]\n{answer_choice}")
    return "\n\n".join(blocks).strip()


def _collect_question_search_terms(payload: str, analysis: Any) -> List[str]:
    terms: List[str] = []
    coordinate = getattr(analysis, "coordinate", None)
    for value in (
        getattr(coordinate, "concept", "") if coordinate else "",
        getattr(coordinate, "chapter", "") if coordinate else "",
        getattr(analysis, "search_query", ""),
    ):
        cleaned = str(value or "").strip()
        if cleaned:
            terms.append(cleaned)
    for entity in getattr(analysis, "entities", None) or []:
        cleaned = str(entity or "").strip()
        if cleaned:
            terms.append(cleaned)
    for token in re.split(r"[^0-9A-Za-z가-힣]+", str(payload or "")):
        cleaned = token.strip()
        if len(cleaned) >= 2 and cleaned not in {"문제", "유사", "설명", "개념", "해설", "찾아", "줘"}:
            terms.append(cleaned)
    seen: set[str] = set()
    out: List[str] = []
    for term in terms:
        norm = _normalize_lookup_text(term)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(term)
        if len(norm) >= 4:
            shortened = term[:-1].strip()
            shortened_norm = _normalize_lookup_text(shortened)
            if shortened_norm and shortened_norm not in seen:
                seen.add(shortened_norm)
                out.append(shortened)
    return out[:12]


async def _find_related_questions(payload: str, analysis: Any, limit: int = 3) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 3), 10))
    coordinate = getattr(analysis, "coordinate", None)
    subject = str(getattr(coordinate, "subject", "") or "").strip()
    terms = _collect_question_search_terms(payload, analysis)
    
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Prepare search terms for similarity matching
        search_text = " ".join(terms) if terms else payload
        
        # Use Postgres trigram similarity for better search results
        if subject:
            # Subject-specific search with similarity scoring
            query = """
                SELECT id, subject, question, option1, option2, option3, option4, answer,
                       ontology_subject, ontology_chapter, ontology_concept,
                       (
                           GREATEST(
                               COALESCE(similarity(question, $1), 0),
                               COALESCE(similarity(option1, $1), 0),
                               COALESCE(similarity(option2, $1), 0),
                               COALESCE(similarity(option3, $1), 0),
                               COALESCE(similarity(option4, $1), 0),
                               COALESCE(similarity(COALESCE(ontology_concept, ''), $1), 0) * 0.8
                           ) +
                           CASE WHEN subject = $2 THEN 0.3 ELSE 0 END +
                           CASE WHEN ontology_subject = $2 THEN 0.2 ELSE 0 END
                       ) as relevance
                FROM questions
                WHERE subject = $2 
                   OR similarity(question, $1) > 0.15
                   OR similarity(option1 || ' ' || option2 || ' ' || option3 || ' ' || option4, $1) > 0.15
                   OR similarity(COALESCE(ontology_concept, ''), $1) > 0.2
                ORDER BY relevance DESC, id ASC
                LIMIT $3
            """
            rows = await conn.fetch(query, search_text, subject, limit + 5)
        else:
            # General search with similarity scoring
            query = """
                SELECT id, subject, question, option1, option2, option3, option4, answer,
                       ontology_subject, ontology_chapter, ontology_concept,
                       (
                           GREATEST(
                               COALESCE(similarity(question, $1), 0),
                               COALESCE(similarity(option1, $1), 0),
                               COALESCE(similarity(option2, $1), 0),
                               COALESCE(similarity(option3, $1), 0),
                               COALESCE(similarity(option4, $1), 0),
                               COALESCE(similarity(COALESCE(ontology_concept, ''), $1), 0) * 0.8
                           )
                       ) as relevance
                FROM questions
                WHERE similarity(question, $1) > 0.15
                   OR similarity(option1 || ' ' || option2 || ' ' || option3 || ' ' || option4, $1) > 0.15
                   OR similarity(COALESCE(ontology_concept, ''), $1) > 0.2
                ORDER BY relevance DESC, id ASC
                LIMIT $2
            """
            rows = await conn.fetch(query, search_text, limit + 5)
    finally:
        await conn.close()

    # Format results
    results = [
        {
            "id": int(row["id"]),
            "subject": str(row["subject"]),
            "question": str(row["question"]),
            "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
            "answer_choice": str(row["answer"]),
        }
        for row in rows[:limit]
    ]
    
    if results:
        return results
    
    # Fallback: Return top questions by subject if no similarity matches found
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if subject:
            fallback_query = """
                SELECT id, subject, question, option1, option2, option3, option4, answer,
                       ontology_subject, ontology_chapter, ontology_concept
                FROM questions
                WHERE subject = $1
                ORDER BY id DESC
                LIMIT $2
            """
            rows = await conn.fetch(fallback_query, subject, limit)
        else:
            fallback_query = """
                SELECT id, subject, question, option1, option2, option3, option4, answer,
                       ontology_subject, ontology_chapter, ontology_concept
                FROM questions
                ORDER BY id DESC
                LIMIT $1
            """
            rows = await conn.fetch(fallback_query, limit)
    finally:
        await conn.close()
    
    return [
        {
            "id": int(row["id"]),
            "subject": str(row["subject"]),
            "question": str(row["question"]),
            "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
            "answer_choice": str(row["answer"]),
        }
        for row in rows
    ]


def _format_question_search_reply(questions: List[Dict[str, Any]], analysis: Any) -> str:
    coordinate = getattr(analysis, "coordinate", None)
    concept = str(getattr(coordinate, "concept", "") or "").strip()
    chapter = str(getattr(coordinate, "chapter", "") or "").strip()
    topic = concept or chapter or "요청 주제"
    if not questions:
        return f"{topic} 기준으로 강한 일치 문제를 아직 찾지 못했어요. 개념명을 조금 더 구체적으로 알려주면 다시 찾아볼게요."
    return (
        f"{topic} 기준으로 관련 문제 {len(questions)}개를 찾았어요.\n\n"
        "원하면 '#1 해설해줘'처럼 번호를 지정해서 바로 이어서 풀이할 수 있어요."
    )


def _build_general_rag_reply(
    *,
    payload: str,
    history: List[Dict[str, str]],
    analysis: Any,
) -> tuple[str, List[EvidenceItem]]:
    query = str(getattr(analysis, "search_query", "") or "").strip() or payload
    coords = _format_analysis_coords(analysis)
    if coords:
        query = f"{query}\n온톨로지 좌표: {coords}"

    embed = OllamaEmbeddings(
        model=settings.OLLAMA_EMBED_MODEL,
        base_url=settings.OLLAMA_HOST,
    )
    db = get_langchain_chroma(embedding_function=embed)
    scored_docs = db.similarity_search_with_relevance_scores(query, k=6)
    docs = [doc for doc, score in scored_docs if score >= 0.25][:4]
    if not docs:
        docs = [doc for doc, _ in scored_docs[:3]]

    evidence = [
        EvidenceItem(id=index + 1, text=str(doc.page_content or "").strip())
        for index, doc in enumerate(docs)
        if str(doc.page_content or "").strip()
    ]
    context = "\n\n".join(
        f"[{item.id}] {item.text[:1400]}" for item in evidence
    )
    history_lines = []
    for message in history[-6:]:
        role = str(message.get("role", "user") or "user").strip()
        content = str(message.get("content", "") or "").strip()
        if content:
            history_lines.append(f"[{role}] {content[:1200]}")
    history_text = "\n".join(history_lines) if history_lines else "-"

    prompt = (
        "당신은 네트워크관리사 학습을 돕는 AI 튜터입니다.\n"
        "반드시 [검색 문맥] 안에서만 설명하고, 문맥에 없는 내용을 단정하지 마세요.\n"
        "답변은 한국어 평문으로 작성하고, 제목 장식 없이 바로 설명하세요.\n"
        "문제 해설 톤이 아니라 GPT/Gemini처럼 자연스러운 일반 답변 형태로 작성하세요.\n"
        "사용자가 초보자면 개념을 먼저 한 줄 요약하고, 그 다음 원리와 예시를 설명하세요.\n\n"
        f"[intent]\n{getattr(analysis, 'intent', '')}\n\n"
        f"[온톨로지 좌표]\n{coords or '-'}\n\n"
        f"[이전 대화]\n{history_text}\n\n"
        f"[검색 문맥]\n{context or '검색 문맥 없음'}\n\n"
        f"[사용자 질문]\n{payload}\n"
    )
    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
        temperature=0,
        num_predict=min(settings.OLLAMA_SOLVE_NUM_PREDICT, 2048),
    )
    reply = str(llm.invoke(prompt, think=False).content or "").strip()
    if not reply:
        reply = str(getattr(analysis, "response_message", "") or "").strip()
    if not reply:
        reply = "질문을 분석했지만 바로 설명을 만들지 못했습니다. 질문을 조금 더 구체적으로 보내 주세요."
    return reply, evidence


def _build_etc_reply(
    *,
    payload: str,
    history: List[Dict[str, str]],
) -> str:
    history_lines = []
    for message in history[-8:]:
        role = str(message.get("role", "user") or "user").strip()
        content = str(message.get("content", "") or "").strip()
        if content:
            history_lines.append(f"[{role}] {content[:1200]}")
    history_text = "\n".join(history_lines) if history_lines else "-"

    prompt = (
        "당신은 Forge AI Tutor입니다.\n"
        "일반 사용자와 자연스럽게 대화하되, 친절하고 정확한 AI 학습 도우미의 정체성은 유지하세요.\n"
        "잡담, 인사, 가벼운 질문, 서비스와 직접 무관한 질문에도 답할 수 있습니다.\n"
        "다만 무리하게 네트워크 자격증 얘기로 끌고 가지는 마세요.\n"
        "답변은 한국어로, 자연스럽고 부담 없게 작성하세요.\n"
        "이전 대화 맥락이 있으면 이어지는 대화처럼 반영하세요.\n"
        "서비스 소개가 필요한 상황이면 사용자가 쉽게 이해할 수 있는 말로 설명하세요.\n\n"
        f"[이전 대화]\n{history_text}\n\n"
        f"[사용자 메시지]\n{payload}\n"
    )
    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
        temperature=0.3,
        num_predict=min(settings.OLLAMA_SOLVE_NUM_PREDICT, 1536),
    )
    reply = str(llm.invoke(prompt, think=False).content or "").strip()
    return reply or "안녕하세요. 편하게 말씀해 주세요. 제가 이해할 수 있는 범위에서 최대한 자연스럽고 정확하게 도와드릴게요."


def _retrieve_general_rag_evidence(
    *,
    payload: str,
    analysis: Any,
) -> tuple[str, str, list[Any], list[EvidenceItem]]:
    query = str(getattr(analysis, "search_query", "") or "").strip() or payload
    coords = _format_analysis_coords(analysis)
    if coords:
        query = f"{query}\n온톨로지 좌표: {coords}"

    embed = OllamaEmbeddings(
        model=settings.OLLAMA_EMBED_MODEL,
        base_url=settings.OLLAMA_HOST,
    )
    db = get_langchain_chroma(embedding_function=embed)
    scored_docs = db.similarity_search_with_relevance_scores(query, k=6)
    docs = [doc for doc, score in scored_docs if score >= 0.25][:4]
    if not docs:
        docs = [doc for doc, _ in scored_docs[:3]]

    evidence = [
        EvidenceItem(id=index + 1, text=str(doc.page_content or "").strip())
        for index, doc in enumerate(docs)
        if str(doc.page_content or "").strip()
    ]
    context = "\n\n".join(
        f"[{item.id}] {item.text[:1400]}" for item in evidence
    )
    return query, coords, docs, evidence


def _build_concept_explain_leg_reply(
    *,
    payload: str,
    history: List[Dict[str, str]],
    analysis: Any,
) -> tuple[dict, list[EvidenceItem], str]:
    _, _, docs, evidence = _retrieve_general_rag_evidence(payload=payload, analysis=analysis)
    context = "\n\n".join(f"[{item.id}] {item.text[:1400]}" for item in evidence)
    history_text = format_history_for_leg_prompt(history, max_chars=6000)
    user_request = payload.strip() or "-"
    prompt = build_concept_explain_leg_prompt(
        context=context or "검색 문맥 없음",
        topic=payload,
        conversation_context=history_text or "-",
        user_message=user_request,
        doc_count=len(docs),
    )
    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
        temperature=0,
        format="json",
        num_predict=min(settings.OLLAMA_SOLVE_NUM_PREDICT, 3072),
    )
    response = llm.invoke(prompt, think=False)
    report = normalize_problem_explain_leg_report(
        extract_problem_explain_leg_json(str(response.content or "").strip())
    )
    if (
        not is_problem_explain_leg_audit_consistent(report)
        or not has_nonempty_problem_explain_leg_refined(report)
    ):
        report = repair_problem_explain_leg_audit(report, docs, llm)
    if not is_problem_explain_leg_body_valid(report):
        raise ValueError("concept_leg_body_invalid")
    return report, evidence, format_concept_explain_leg_for_chat(report)
    asyncio.create_task(log_api_request_jsonl(
        endpoint=endpoint,
        method=method,
        user_id=user_id,
        request_payload=request_payload,
        response_payload=response_payload,
        status_code=status_code,
        error_message=error_message,
        response_time_ms=response_time_ms,
    ))

async def _rag_startup_warmup() -> None:
    """
    첫 실제 사용자 요청 전에 Ollama에 짧은 생성을 한 번 보내 콜드 스타트 완화.
    AI 모델은 첫 실행 시 로딩 시간이 깁니다.
    서버가 켜질 때 아무 의미 없는 마침표(.)를 하나 던져서 모델을 미리 메모리에 올려두는 "예열" 과정입니다.
    
    - model: 사용할 Ollama 모델명
    - base_url: Ollama 서버 주소
    - temperature: 모델의 창의성(0=고정, 1=자유)
    - num_predict: 최대 생성 토큰 수
    
    예외 발생 시 서비스에는 영향 없음.
    """
    await asyncio.sleep(1.0) # 앱 초기화 안정화 대기
    try:
        from langchain_ollama import ChatOllama

        def _ping() -> None:
            chat = ChatOllama(
                model=settings.OLLAMA_MODEL,  # 사용할 Ollama 모델명
                base_url=settings.OLLAMA_HOST, # Ollama 서버 주소
                temperature=0,  # 이 값은 모델이 단어를 선택할 때 얼마나 확률적으로(창의적으로) 행동할지를 결정합니다. 범위는 보통 0에서 2 사이입니다.
                num_predict=24, # 모델이 최대 몇 개의 토큰(단어 조각)을 생성할지 제한하는 설정입니다.
            )
            chat.invoke(".", think=False)

        loop = asyncio.get_event_loop() # 이벤트 루프 호출
        await asyncio.wait_for(loop.run_in_executor(None, _ping), timeout=120.0) # 별도의 스레드에서 _ping 실행, 최대 120초 대기(sub thread)
        print("[RAG warmup] ollama short invoke ok")
    except Exception as exc:
        print("[RAG warmup] skipped:", exc)





@asynccontextmanager
async def _app_lifespan(app):
    asyncio.create_task(_rag_startup_warmup())
    yield



# FastAPI 앱 인스턴스 및 미들웨어 설정
app = FastAPI(title="sikdorak-python-api", version="1.0.0", lifespan=_app_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 운영 환경에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next: Callable) -> Response:
    """
    모든 요청/응답을 DB에 로깅합니다 (health 체크 등은 제외).
    - POST/PUT 본문 재구성, JSON 응답 본문 캡처, 비동기 로깅
    - 예외 발생 시에도 로깅
    """
    start_time = time.time()
    endpoint = request.url.path
    method = request.method
    request_payload = None
    user_id = None
    # POST/PUT 요청 본문 캡처 (body는 한 번만 읽을 수 있으므로 재구성)
    if method in ["POST", "PUT"]:
        try:
            raw_body = await request.body()
            if raw_body:
                request_payload = json.loads(raw_body)
            # body를 다시 읽을 수 있도록 receive 재설정
            async def _replay_receive():
                return {"type": "http.request", "body": raw_body, "more_body": False}
            request = Request(request.scope, receive=_replay_receive)
        except Exception:
            pass
    try:
        response = await call_next(request)
        status_code = response.status_code
        response_payload = None
        # JSON 응답 본문 캡처
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                body_bytes = b"".join(chunks)
                if body_bytes:
                    response_payload = json.loads(body_bytes)
                # 소비된 body를 복원
                response = Response(
                    content=body_bytes,
                    status_code=status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception:
                pass
        response_time_ms = (time.time() - start_time) * 1000
        _dispatch_api_logs(
            endpoint=endpoint, method=method, user_id=user_id,
            request_payload=request_payload, response_payload=response_payload,
            status_code=status_code, response_time_ms=response_time_ms,
        )
        return response
    except Exception as exc:
        response_time_ms = (time.time() - start_time) * 1000
        _dispatch_api_logs(
            endpoint=endpoint, method=method, user_id=user_id,
            request_payload=request_payload, status_code=500,
            error_message=str(exc), response_time_ms=response_time_ms,
        )
        raise


@app.get("/health", response_model=HealthResponse)
@app.get("/healthz", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    서비스 헬스체크 엔드포인트.
    동기 RAG가 스레드풀을 다 써도 헬스는 즉시 응답 (모니터링/로드밸런서용).
    """
    return HealthResponse(status="ok", service="sikdorak-python-api")



@app.post("/api/rag/solve", response_model=SolveResponse)
@app.post("/api/v1/rag/solve", response_model=SolveResponse)
def rag_solve(payload: SolveRequest) -> SolveResponse:
        """
        시험 문제 목록을 받아 RAG 기반 해설 JSON을 반환합니다.
        - 병렬성 제어(semaphore)로 SQLite busy/timeout 방지
        - 예외 발생 시 HTTP 500 반환
        """
        try:
                with _rag_solve_semaphore:
                        results = solve_items(payload.items, force_rebuild=payload.rebuild_db)
                return SolveResponse(ok=True, total=len(results), results=results)
        except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc


class ForgeAnalyzeRequest(BaseModel):
    payload: str
    history: List[Dict[str, str]] = Field(default_factory=list)
    conversation_key: str | None = None


@app.post("/api/forge/analyze")
@app.post("/api/v1/forge/analyze")
@app.post("/api/ontology/analyze")
@app.post("/api/v1/ontology/analyze")
async def forge_analyze(body: ForgeAnalyzeRequest):
    """
    사용자 발화를 통합 의도/지식 좌표 JSON으로 분석합니다.
    - 후속 턴에 문제 본문만 오면 온톨로지 입력에 맥락 문구를 덧붙입니다(파싱·LEG는 원문 기준).
    - EXPLAIN_PROBLEM 이거나, 이전에 해설 요청이 있었고 4지 형식이면 LEG 해설을 생성합니다.
    """
    hist = body.history or []
    payload_raw = str(body.payload or "").strip()
    payload_user = _strip_mock_exam_context_block(payload_raw)
    mock_context_probe = _extract_mock_exam_context(payload_raw, hist)
    if _wants_mock_exam_analysis(payload_raw, hist, None):
        mock_exam_out = await _handle_mock_exam_analysis(payload_raw, hist, None)
        if mock_exam_out is not None:
            return mock_exam_out
    payload_onto = augment_payload_for_ontology_followup(payload_user, hist)
    result = await _forge_ontology_engine.analyze(
        payload=payload_onto,
        history=hist,
    )

    intent_sequence = _analysis_intent_sequence(result)
    if _wants_mock_exam_analysis(payload_raw, hist, result):
        mock_exam_out = await _handle_mock_exam_analysis(payload_raw, hist, result)
        if mock_exam_out is not None:
            mock_exam_out["analysis"] = result.model_dump()
            return mock_exam_out

    out: Dict[str, Any] = {"ok": True, "analysis": result.model_dump()}
    if str(getattr(result, "status", "") or "") != "COMPLETE":
        out["assistant_message"] = (
            str(getattr(result, "response_message", "") or "").strip()
            or "질문을 이해하기에 정보가 조금 부족해요. 문제 본문이나 궁금한 개념을 조금 더 구체적으로 보내 주세요."
        )
        return out

    if str(getattr(result, "intent", "") or "") == "ETC":
        out["assistant_message"] = build_etc_reply_external(
            payload=payload_user,
            history=hist,
        )
        out["route"] = "ontology>etc"
        return out

    wants_question_search = _wants_question_search(payload_user, result)

    payload_resolved = _resolve_referenced_question_payload(payload_user, hist)
    item = None
    try:
        item = try_build_exam_item_for_explain_problem(payload_resolved, result)
    except Exception:
        item = None
    leg_message = ""
    leg_route = ""
    leg_payload: Dict[str, Any] = {}
    has_explain_problem_stage = "EXPLAIN_PROBLEM" in intent_sequence
    has_concept_explain_stage = "CONCEPT_EXPLAIN" in intent_sequence

    if item is not None:
        conv = format_history_for_leg_prompt(hist)
        base_um = str(getattr(item, "user_message", "") or "").strip() or payload_user
        merged_parts = []
        if conv:
            merged_parts.append(f"[이전 대화 맥락]\n{conv}")
        if base_um:
            merged_parts.append(f"[이번 사용자 입력·추가 요청]\n{base_um}")
        merged = "\n\n".join(merged_parts).strip()
        if merged:
            try:
                max_um = int(os.getenv("FORGE_LEG_USER_MESSAGE_MAX_CHARS", "14000").strip() or "14000")
            except ValueError:
                max_um = 14000
            merged = merged[: max(1000, max_um)]
            item = ExamItem(**{**item.model_dump(), "user_message": merged})
        intent_now = str(getattr(result, "intent", "") or "")
        explain_hint = any(keyword in payload_raw for keyword in ("해설", "설명", "개념", "풀이", "알려줘", "알려줘요", "정리"))
        allow_leg = (
            has_explain_problem_stage
            or has_concept_explain_stage
            or intent_now in {"EXPLAIN_PROBLEM", "CONCEPT_EXPLAIN", "FOLLOWUP"}
            or history_suggests_problem_explain(hist)
            or explain_hint
        )
        if allow_leg:
            try:
                with _rag_solve_semaphore:
                    solved = solve_items([item], force_rebuild=False)
                if solved:
                    sr = solved[0]
                    leg_payload = {
                        "report": sr.report,
                        "evidence": [e.model_dump() for e in sr.evidence],
                    }
                    leg_message = format_leg_report_for_chat(sr.report)
                    leg_route = "ontology>rag>leg"
            except Exception:
                pass

    if leg_message and wants_question_search:
        questions = await _find_related_questions(
            payload=payload_user,
            analysis=result,
            limit=_extract_requested_question_count(payload_user),
        )
        out["leg"] = leg_payload
        out["recommended_questions"] = questions
        out["assistant_message"] = (
            f"{leg_message}\n\n"
            f"{_format_question_search_reply(questions, result)}"
        )
        out["route"] = f"{leg_route}+db>question-search"
        return out

    if leg_message:
        out["leg"] = leg_payload
        out["assistant_message"] = leg_message
        out["route"] = leg_route
        return out

    allow_concept_leg = item is None and (
        has_concept_explain_stage
        or str(getattr(result, "intent", "") or "") in {
            "CONCEPT_EXPLAIN",
            "FOLLOWUP",
        }
    )
    allow_question_block_concept_leg = (
        item is None
        and _payload_has_question_block(payload_resolved)
        and any(keyword in payload_user for keyword in ("해설", "설명", "개념", "풀이", "알려", "정리"))
    )

    if wants_question_search and (allow_concept_leg or allow_question_block_concept_leg):
        try:
            report, evidence, assistant_message = _build_concept_explain_leg_reply(
                payload=payload_resolved,
                history=hist,
                analysis=result,
            )
            questions = await _find_related_questions(
                payload=payload_user,
                analysis=result,
                limit=_extract_requested_question_count(payload_user),
            )
            out["leg"] = {
                "report": report,
                "evidence": [item.model_dump() for item in evidence],
            }
            out["assistant_message"] = f"{assistant_message}\n\n{_format_question_search_reply(questions, result)}"
            out["recommended_questions"] = questions
            out["route"] = "ontology>rag>concept-leg+db>question-search"
            return out
        except Exception:
            pass

    if wants_question_search:
        questions = await _find_related_questions(
            payload=payload_user,
            analysis=result,
            limit=_extract_requested_question_count(payload_user),
        )
        out["assistant_message"] = _format_question_search_reply(questions, result)
        out["recommended_questions"] = questions
        out["route"] = "ontology>db>question-search"
        return out

    if allow_concept_leg or allow_question_block_concept_leg:
        try:
            report, evidence, assistant_message = _build_concept_explain_leg_reply(
                payload=payload_resolved,
                history=hist,
                analysis=result,
            )
            out["leg"] = {
                "report": report,
                "evidence": [item.model_dump() for item in evidence],
            }
            out["assistant_message"] = assistant_message
            out["route"] = "ontology>rag>concept-leg"
            return out
        except Exception:
            pass

    try:
        assistant_message, evidence = _build_general_rag_reply(
            payload=payload_user,
            history=hist,
            analysis=result,
        )
        out["assistant_message"] = assistant_message
        out["rag"] = {
            "evidence": [item.model_dump() for item in evidence],
        }
        out["route"] = "ontology>rag"
    except Exception:
        out["assistant_message"] = (
            str(getattr(result, "response_message", "") or "").strip()
            or "질문을 분석했지만 답변 생성 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
        )
    return out


class ProblemExplainLegRequest(BaseModel):
    q: str
    opts: List[str] = Field(default_factory=list)
    wrong: str = "-"
    ans: str = "-"
    rebuild_db: bool = False
    search_query: str = ""
    user_message: str = ""
    ontology_subject: str = ""
    ontology_chapter: str = ""
    ontology_concept: str = ""
    ontology_coordinates: List[Dict[str, str]] = Field(default_factory=list)


@app.post("/api/leg/explain")
@app.post("/api/v1/leg/explain")
def problem_explain_leg(body: ProblemExplainLegRequest):
    """
    Problem_Explain_LEG 전용 단건 해설 엔드포인트.
    """
    if not body.q.strip():
        raise HTTPException(status_code=400, detail="q는 비어 있을 수 없습니다.")
    if len(body.opts) != 4:
        raise HTTPException(status_code=400, detail="opts는 4개 항목이어야 합니다.")
    opt_values = [str(x or "").strip() for x in body.opts]
    if any(not x for x in opt_values):
        raise HTTPException(status_code=400, detail="opts 4개는 모두 비어있지 않아야 합니다.")

    item = ExamItem(
        q=body.q.strip(),
        opts=", ".join([f"{idx + 1}) {text}" for idx, text in enumerate(opt_values)]),
        wrong=str(body.wrong or "-").strip() or "-",
        ans=str(body.ans or "-").strip() or "-",
        search_query=str(body.search_query or "").strip() or None,
        user_message=str(body.user_message or "").strip() or None,
        ontology_subject=str(body.ontology_subject or "").strip() or None,
        ontology_chapter=str(body.ontology_chapter or "").strip() or None,
        ontology_concept=str(body.ontology_concept or "").strip() or None,
        ontology_coordinates=[
            {
                "subject": str(c.get("subject", "")).strip(),
                "chapter": str(c.get("chapter", "")).strip(),
                "concept": str(c.get("concept", "")).strip(),
            }
            for c in (body.ontology_coordinates or [])
            if isinstance(c, dict)
        ] or None,
    )
    with _rag_solve_semaphore:
        results = solve_items([item], force_rebuild=body.rebuild_db)
    first = results[0] if results else None
    return {
        "ok": True,
        "engine": "Problem_Explain_LEG",
        "result": first.model_dump() if first else None,
    }


class GemmaThinkStreamRequest(BaseModel):
    prompt: str
    history: List[Dict[str, str]] = Field(default_factory=list)


@app.post("/api/leg/think-stream")
@app.post("/api/v1/leg/think-stream")
def leg_think_stream(body: GemmaThinkStreamRequest):
    """
    Gemma think 과정을 SSE로 스트리밍합니다.
    """
    prompt = str(body.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt는 비어 있을 수 없습니다.")
    history = body.history[-8:] if body.history else []
    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
        temperature=0,
    )
    merged = []
    for msg in history:
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", "")).strip()
        if content:
            merged.append(f"[{role}] {content}")
    merged.append(f"[user] {prompt}")
    composed_prompt = "\n".join(merged)
    reasoning_prompt = (
        "너는 네트워크 자격증 문제를 풀이하는 튜터다.\n"
        "요청된 문제를 보고 '실시간 진행 로그'처럼 짧은 단계 문장으로만 출력하라.\n"
        "- 매 줄은 한 단계\n"
        "- 아직 확정 답안을 단정하지 말고 검토 과정 위주로 작성\n"
        "- 불필요한 서두 없이 바로 단계 출력\n\n"
        f"{composed_prompt}"
    )

    def generate():
        yield "event: meta\ndata: {\"ok\":true,\"engine\":\"Problem_Explain_LEG\",\"model\":\"" + settings.OLLAMA_MODEL + "\"}\n\n"
        try:
            for chunk in llm.stream(reasoning_prompt):
                text = ""
                if hasattr(chunk, "content") and isinstance(chunk.content, str):
                    text = chunk.content
                # 일부 Ollama/LangChain 조합은 thinking 토큰을 additional_kwargs에 담아 전달함
                if not text and hasattr(chunk, "additional_kwargs") and isinstance(chunk.additional_kwargs, dict):
                    text = (
                        chunk.additional_kwargs.get("thinking")
                        or chunk.additional_kwargs.get("reasoning")
                        or chunk.additional_kwargs.get("thought")
                        or ""
                    )
                if not text:
                    continue
                payload = json.dumps({"chunk": str(text)}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as exc:
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {payload}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _run_rag_job_bg(job_id: int, exam_item: ExamItem, rebuild_db: bool) -> None:
    """백그라운드에서 RAG 해설 생성 후 DB 업데이트. 클라이언트 연결 해제와 무관하게 실행됨."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        try:
            # solve_items는 무거운 동기 함수 → 스레드풀에서 실행해야 이벤트 루프를 블록하지 않음
            loop = asyncio.get_event_loop()
            def _solve_one_slot() -> list:
                with _rag_solve_semaphore:
                    return solve_items([exam_item], force_rebuild=rebuild_db)

            results = await loop.run_in_executor(None, _solve_one_slot)
            result_payload = {
                "ok": True,
                "total": len(results),
                "results": jsonable_encoder(results),
            }
            await conn.execute(
                """
                UPDATE rag_solve_jobs
                SET status = 'completed',
                    result_payload = $2::jsonb,
                    completed_at = NOW()
                WHERE id = $1
                """,
                job_id,
                json.dumps(result_payload, ensure_ascii=False),
            )
        except Exception as solve_exc:
            await conn.execute(
                """
                UPDATE rag_solve_jobs
                SET status = 'failed',
                    error_message = $2,
                    completed_at = NOW()
                WHERE id = $1
                """,
                job_id,
                str(solve_exc),
            )
    finally:
        await conn.close()


@app.post("/api/rag/jobs")
async def create_rag_job(request: Request, background_tasks: BackgroundTasks):
    """
    프론트엔드 AI 해설 생성 요청을 받아 jobId를 즉시 반환합니다.
    해설 생성은 백그라운드에서 진행되므로 사용자가 페이지를 떠나도 처리가 완료됩니다.
    """
    try:
        session_user = await _get_session_user_from_request(request)
        if not session_user or not session_user.get("id"):
            raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

        body = await request.json()
        question = str(body.get("question") or "").strip()
        options = body.get("options") or []
        wrong_choice = str(body.get("wrongChoice") or "").strip()
        answer_choice = str(body.get("answerChoice") or "").strip()
        rebuild_db = bool(body.get("rebuild_db", False))
        raw_attempt_id = body.get("attemptId")
        raw_answer_idx = body.get("answerIndex")
        quiz_attempt_id = None
        quiz_attempt_answer_index = None
        try:
            if raw_attempt_id is not None and str(raw_attempt_id).strip() != "":
                quiz_attempt_id = int(raw_attempt_id)
        except (TypeError, ValueError):
            quiz_attempt_id = None
        try:
            if raw_answer_idx is not None and str(raw_answer_idx).strip() != "":
                quiz_attempt_answer_index = int(raw_answer_idx)
        except (TypeError, ValueError):
            quiz_attempt_answer_index = None

        if not question:
            raise HTTPException(status_code=400, detail="문제를 입력해주세요.")
        if not isinstance(options, list) or len(options) != 4:
            raise HTTPException(status_code=400, detail="보기 4개를 모두 입력해주세요.")

        opt_values = [str(x or "").strip() for x in options]
        if any(not x for x in opt_values):
            raise HTTPException(status_code=400, detail="보기 4개를 모두 입력해주세요.")

        opts_text = ", ".join([f"{idx + 1}) {text}" for idx, text in enumerate(opt_values)])
        exam_item = ExamItem(
            q=question,
            opts=opts_text,
            wrong=wrong_choice,
            ans=answer_choice,
        )

        # 1) processing 상태로 job 즉시 생성 후 jobId 반환
        user_id = int(session_user["id"])

        conn = await asyncpg.connect(DATABASE_URL)
        try:
            req_payload = {
                "question": question,
                "options": opt_values,
                "wrongChoice": wrong_choice,
                "answerChoice": answer_choice,
                "rebuild_db": rebuild_db,
            }
            if quiz_attempt_id is not None:
                req_payload["attemptId"] = quiz_attempt_id
            if quiz_attempt_answer_index is not None:
                req_payload["answerIndex"] = quiz_attempt_answer_index

            # quiz_attempt_* 컬럼이 없는 구 DB에서도 동작하도록 최소 컬럼만 INSERT
            row = await conn.fetchrow(
                """
                INSERT INTO rag_solve_jobs
                (user_id, status, question_text, option_1, option_2, option_3, option_4,
                 wrong_choice, answer_choice, request_payload, started_at, created_at)
                VALUES
                ($1, 'processing', $2, $3, $4, $5, $6,
                 $7, $8, $9::jsonb, NOW(), NOW())
                RETURNING id
                """,
                user_id,
                question,
                opt_values[0],
                opt_values[1],
                opt_values[2],
                opt_values[3],
                wrong_choice,
                answer_choice,
                json.dumps(req_payload, ensure_ascii=False),
            )
            job_id = int(row["id"])

            # 컬럼이 있으면 퀴즈 연동 값만 보강
            try:
                await conn.execute(
                    """
                    UPDATE rag_solve_jobs
                    SET quiz_attempt_id = $2, quiz_attempt_answer_index = $3
                    WHERE id = $1
                    """,
                    job_id,
                    quiz_attempt_id,
                    quiz_attempt_answer_index,
                )
            except Exception:
                pass
        finally:
            await conn.close()

        # 2) 해설 생성은 백그라운드로 위임 — 클라이언트 종료와 무관하게 완료됨
        background_tasks.add_task(_run_rag_job_bg, job_id, exam_item, rebuild_db)

        return {"ok": True, "jobId": job_id}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print("[ERROR] /api/rag/jobs 500:", exc)
        print(tb)
        # 클라이언트에도 Traceback 일부 반환
        raise HTTPException(status_code=500, detail=f"{exc}\n{tb}") from exc

@app.post("/api/v1/test/save")
async def save_test_results(request: Request):
    """
    테스트 결과를 API 로그에 저장 (웹 대시보드에 표시)
    
    요청 예시:
    {
      "test_name": "최종 RAG 테스트",
      "total_questions": 10,
      "success_count": 10,
      "avg_elapsed_sec": 45.43,
      "results_file": "/path/to/results.json"
    }
    """
    try:
        body = await request.json()
        
        # 사용자 인증 (선택사항)
        user_id = request.headers.get("X-User-Id", "13")  # deamon user 기본값
        
        # 테스트 요약
        summary = {
            "test_name": body.get("test_name", "RAG Test"),
            "total_questions": body.get("total_questions"),
            "success_count": body.get("success_count"),
            "avg_elapsed_sec": body.get("avg_elapsed_sec"),
            "verdict_distribution": body.get("verdict_distribution", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        # API 로그에 저장
        await log_api_request(
            endpoint="/api/v1/test/save",
            method="POST",
            request_payload=body,
            response_payload=summary,
            status_code=200,
            user_id=int(user_id)
        )
        
        return {"ok": True, "message": "테스트 결과 저장 완료", "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

@app.get("/api/v1/test/history")
async def get_test_history(user_id: int = 13, limit: int = 20):
    """
    사용자의 테스트 결과 이력 조회 (웹 대시보드에 표시)
    """
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            results = await conn.fetch(
                """
                SELECT id, endpoint, request_payload, response_payload, status_code, response_time_ms, created_at
                FROM api_request_logs
                WHERE user_id = $1 AND endpoint LIKE '/api/v1/test/%'
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit
            )
            
            history = []
            for row in results:
                history.append({
                    "id": row["id"],
                    "endpoint": row["endpoint"],
                    "test_name": row["response_payload"].get("test_name") if row["response_payload"] else None,
                    "total_questions": row["response_payload"].get("total_questions") if row["response_payload"] else None,
                    "success_count": row["response_payload"].get("success_count") if row["response_payload"] else None,
                    "avg_elapsed_sec": row["response_payload"].get("avg_elapsed_sec") if row["response_payload"] else None,
                    "response_time_ms": row["response_time_ms"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None
                })
            
            return {"ok": True, "total": len(history), "history": history}
        finally:
            await conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/rag/history")
async def get_rag_solve_history(user_id: int = 13, limit: int = 300):
    """
    사용자의 AI 해설 기록 조회 (웹 대시보드용)
    """
    try:
        limit = min(int(limit), 300)
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            results = await conn.fetch(
                """
                SELECT id, status, question_text, 
                       option_1, option_2, option_3, option_4,
                       wrong_choice, answer_choice, result_payload,
                       created_at
                FROM rag_solve_jobs
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit
            )
            
            jobs = []
            for row in results:
                jobs.append({
                    "id": row["id"],
                    "status": row["status"],
                    "questionText": row["question_text"],
                    "option1": row["option_1"],
                    "option2": row["option_2"],
                    "option3": row["option_3"],
                    "option4": row["option_4"],
                    "wrongChoice": row["wrong_choice"],
                    "answerChoice": row["answer_choice"],
                    "resultPayload": row["result_payload"],
                    "createdAt": row["created_at"].isoformat() if row["created_at"] else None
                })
            
            return {"ok": True, "total": len(jobs), "jobs": jobs}
        finally:
            await conn.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/rag/jobs/{job_id}")
async def get_rag_job_detail(request: Request, job_id: int):
    """
    특정 AI 해설 작업의 상세 정보 조회
    """
    session_user = await _get_session_user_from_request(request)
    if not session_user or not session_user.get("id"):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id = int(session_user["id"])
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            row = await conn.fetchrow(
                """
                SELECT id, status, question_text,
                       option_1, option_2, option_3, option_4,
                       wrong_choice, answer_choice, result_payload,
                       error_message, created_at
                FROM rag_solve_jobs
                WHERE id = $1 AND user_id = $2
                """,
                job_id,
                user_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="해설 기록을 찾을 수 없습니다")
            
            job = {
                "id": row["id"],
                "status": row["status"],
                "questionText": row["question_text"],
                "option1": row["option_1"],
                "option2": row["option_2"],
                "option3": row["option_3"],
                "option4": row["option_4"],
                "wrongChoice": row["wrong_choice"],
                "answerChoice": row["answer_choice"],
                "resultPayload": row["result_payload"],
                "errorMessage": row["error_message"],
                "createdAt": row["created_at"].isoformat() if row["created_at"] else None
            }
            
            return {"ok": True, "job": job}
        finally:
            await conn.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ChatSyncRequest(BaseModel):
    username: str
    conversations: List[Dict[str, Any]] = Field(default_factory=list)


class MockExamGenerateRequest(BaseModel):
    subject_counts: Optional[Dict[str, int]] = None
    seed: Optional[int] = None


class MockExamSubmitAnswer(BaseModel):
    question_id: int
    selected_index: Optional[int] = None


class MockExamSubmitRequest(BaseModel):
    quiz_uid: str
    duration_sec: int = 0
    answers: List[MockExamSubmitAnswer] = Field(default_factory=list)


def _safe_username_from_header(request: Request) -> str:
    username = str(request.headers.get("X-Session-User", "") or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="X-Session-User header is required.")
    if len(username) > 100:
        raise HTTPException(status_code=400, detail="username is too long.")
    return username


MOCK_EXAM_DEFAULT_SUBJECT_COUNTS: Dict[str, int] = {
    "1과목": 17,
    "2과목": 18,
    "3과목": 10,
    "4과목": 5,
}


def _normalize_subject_counts(raw: Optional[Dict[str, int]]) -> Dict[str, int]:
    if not raw:
        return dict(MOCK_EXAM_DEFAULT_SUBJECT_COUNTS)

    out: Dict[str, int] = {}
    for subject, count in raw.items():
        key = str(subject or "").strip()
        if key not in MOCK_EXAM_DEFAULT_SUBJECT_COUNTS:
            continue
        try:
            safe_count = int(count)
        except (TypeError, ValueError):
            continue
        if safe_count > 0:
            out[key] = safe_count

    if not out:
        return dict(MOCK_EXAM_DEFAULT_SUBJECT_COUNTS)

    if sum(out.values()) != 50:
        raise HTTPException(status_code=400, detail="subject_counts total must be exactly 50.")
    return out


def _mock_exam_chat_followup(result_rows: List[Dict[str, Any]], subject_stats: Dict[str, Dict[str, int]]) -> str:
    wrong_rows = [row for row in result_rows if not row.get("is_correct")]
    weak_subjects = sorted(
        subject_stats.items(),
        key=lambda item: (item[1].get("correct", 0) / max(1, item[1].get("total", 1))),
    )
    weak_subject_text = ", ".join(subject for subject, _ in weak_subjects[:2])

    if not wrong_rows:
        return (
            "모의고사 결과를 채팅에 이어서 보내줘. 전부 정답이었고, "
            "동일 난이도 실전형 10문제를 추가로 풀고 싶어. 바로 전체 해설로 넘어가지 말고 다음 학습 방향부터 짧게 정리해줘."
        )

    sample = wrong_rows[0]
    sample_question = str(sample.get("question") or "").strip()
    sample_question = sample_question[:120]
    selected = sample.get("selected_index")
    correct = sample.get("correct_index")
    return (
        "모의고사 결과를 이어서 분석해줘. "
        f"취약 과목은 {weak_subject_text or '없음'}이고, "
        f"틀린 문제 예시는 '{sample_question}'야. "
        f"내 선택은 {selected}, 정답은 {correct}였어. "
        "전체 오답을 한 번에 모두 해설하지는 말고, 먼저 약점 요약과 학습 우선순위를 정리한 뒤 내가 선택한 문제부터 하나씩 복기할 수 있게 진행해줘."
    )


def _coerce_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_mock_exam_context_from_text(text: str) -> Dict[str, Any]:
    raw = str(text or "")
    if not raw:
        return {}

    pattern = re.compile(
        re.escape(MOCK_EXAM_CONTEXT_START) + r"\s*(.*?)\s*" + re.escape(MOCK_EXAM_CONTEXT_END),
        re.DOTALL,
    )
    matches = pattern.findall(raw)
    if not matches:
        return {}

    # Prefer the latest embedded context block when multiple snapshots exist.
    for blob in reversed(matches):
        try:
            decoded = json.loads(str(blob).strip())
            if isinstance(decoded, dict):
                return decoded
        except Exception:
            continue
    return {}


def _extract_mock_exam_context(payload: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
    context = _extract_mock_exam_context_from_text(payload)
    if context:
        return context

    history = history or []
    for item in reversed(history):
        context = _extract_mock_exam_context_from_text(str(item.get("content") or ""))
        if context:
            return context

    # Fallback for edge cases where start/end markers got split across messages.
    merged_history = "\n\n".join(str(item.get("content") or "") for item in history)
    if merged_history:
        context = _extract_mock_exam_context_from_text(merged_history)
        if context:
            return context
    return {}


def _extract_mock_question_numbers(payload: str) -> List[int]:
    numbers = [int(value) for value in re.findall(r"(\d{1,2})\s*번", str(payload or ""))]
    out: List[int] = []
    for value in numbers:
        if 1 <= value <= 50 and value not in out:
            out.append(value)
    return out


def _extract_mock_subject_label(payload: str) -> str:
    match = re.search(r"([1-4]과목)", str(payload or ""))
    return str(match.group(1)) if match else ""


def _mock_context_questions(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    questions = context.get("questions") or []
    return questions if isinstance(questions, list) else []


def _mock_find_question(context: Dict[str, Any], exam_index: int) -> Dict[str, Any]:
    for item in _mock_context_questions(context):
        try:
            if int(item.get("exam_index") or 0) == int(exam_index):
                return item
        except (TypeError, ValueError):
            continue
    return {}


def _payload_wants_mock_numbered_explain(payload: str) -> bool:
    numbers = _extract_mock_question_numbers(payload)
    if not numbers:
        return False
    text = _normalize_lookup_text(payload)
    return any(keyword in text for keyword in ("해설", "풀이", "설명", "복기", "왜", "정답", "오답"))


def _build_mock_numbered_leg_reply(context: Dict[str, Any], payload_raw: str) -> Optional[Dict[str, Any]]:
    if not _payload_wants_mock_numbered_explain(payload_raw):
        return None

    numbers = _extract_mock_question_numbers(payload_raw)
    focus_rows: List[tuple[int, Dict[str, Any]]] = []
    missing: List[int] = []
    for num in numbers[:3]:
        row = _mock_find_question(context, num)
        if row:
            focus_rows.append((num, row))
        else:
            missing.append(num)

    if not focus_rows:
        return {
            "ok": True,
            "assistant_message": "요청한 문항 번호를 현재 모의고사 기록에서 찾지 못했어요. 번호를 다시 확인해 주세요.",
            "route": "mock-exam>numbered-leg:not-found",
        }

    exam_items: List[ExamItem] = []
    valid_rows: List[tuple[int, Dict[str, Any]]] = []
    for num, row in focus_rows:
        question = str(row.get("question") or "").strip()
        options = [str(opt or "").strip() for opt in (row.get("options") or [])][:4]
        if not question or len(options) != 4 or any(not opt for opt in options):
            continue

        try:
            selected_index = int(row.get("selected_index")) if row.get("selected_index") is not None else None
        except (TypeError, ValueError):
            selected_index = None
        try:
            correct_index = int(row.get("correct_index")) if row.get("correct_index") is not None else None
        except (TypeError, ValueError):
            correct_index = None

        def _choice_text(idx: Optional[int]) -> str:
            if idx is None or idx < 1 or idx > 4:
                return "-"
            return f"{idx}) {options[idx - 1]}"

        item = ExamItem(
            q=question,
            opts=", ".join(f"{idx + 1}) {opt}" for idx, opt in enumerate(options)),
            wrong=(_choice_text(selected_index) if selected_index is not None else "미응답"),
            ans=_choice_text(correct_index),
            user_message=(
                f"모의고사 {num}번 문항 해설 요청입니다. "
                "정답 근거와 오답 포인트를 초보자도 이해하기 쉽게 설명해 주세요."
            ),
            ontology_subject=str(row.get("ontology_subject") or "").strip() or None,
            ontology_chapter=str(row.get("ontology_chapter") or "").strip() or None,
            ontology_concept=str(row.get("ontology_concept") or "").strip() or None,
        )
        exam_items.append(item)
        valid_rows.append((num, row))

    if not exam_items:
        return {
            "ok": True,
            "assistant_message": "요청한 번호의 문제 데이터가 불완전해서 해설을 만들 수 없었어요. 다른 번호로 다시 요청해 주세요.",
            "route": "mock-exam>numbered-leg:invalid-item",
        }

    sections: List[str] = []
    leg_reports: List[Dict[str, Any]] = []
    try:
        with _rag_solve_semaphore:
            solved = solve_items(exam_items, force_rebuild=False)
        for (num, row), solved_row in zip(valid_rows, solved):
            selected = row.get("selected_index")
            correct = row.get("correct_index")
            sections.append(
                f"[{num}번 문제] 내선택 {selected if selected is not None else '미응답'} / 정답 {correct if correct is not None else '-'}"
            )
            sections.append(format_leg_report_for_chat(solved_row.report))
            leg_reports.append(
                {
                    "exam_index": num,
                    "report": solved_row.report,
                    "evidence": [item.model_dump() for item in solved_row.evidence],
                }
            )
    except Exception:
        for num, row in valid_rows:
            selected = row.get("selected_index")
            correct = row.get("correct_index")
            sections.append(
                f"[{num}번 문제] 내선택 {selected if selected is not None else '미응답'} / 정답 {correct if correct is not None else '-'}"
            )
            sections.append("해설 생성 중 오류가 발생했습니다. 해당 번호로 다시 요청해 주세요.")

    if missing:
        sections.append(f"참고: {', '.join(f'{n}번' for n in missing)}은(는) 현재 모의고사 기록에서 찾지 못했어요.")

    out: Dict[str, Any] = {
        "ok": True,
        "assistant_message": "\n\n".join(sections).strip(),
        "route": "mock-exam>numbered-leg",
    }
    if len(leg_reports) == 1:
        out["leg"] = {
            "report": leg_reports[0]["report"],
            "evidence": leg_reports[0]["evidence"],
        }
    elif leg_reports:
        out["legs"] = leg_reports
    return out


def _mock_wrong_questions(context: Dict[str, Any], subject_prefix: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in _mock_context_questions(context):
        if bool(item.get("is_correct")):
            continue
        subject = str(item.get("subject") or "")
        if subject_prefix and not subject.startswith(subject_prefix):
            continue
        out.append(item)
    return out


def _payload_wants_question_search(payload: str) -> bool:
    normalized = _normalize_lookup_text(payload)
    if not normalized:
        return False
    compact = normalized.replace(" ", "")
    return any(
        _normalize_lookup_text(keyword) in normalized
        or _normalize_lookup_text(keyword).replace(" ", "") in compact
        for keyword in QUESTION_SEARCH_KEYWORDS
    )


def _build_mock_exam_context_for_leg(context: Dict[str, Any], payload_raw: str) -> str:
    subject_stats = context.get("subject_stats") or {}
    wrong_items = _mock_wrong_questions(context)
    numbers = _extract_mock_question_numbers(payload_raw)
    focused = [_mock_find_question(context, num) for num in numbers[:3]]
    focused = [item for item in focused if item]

    lines = [
        f"점수: {int(context.get('score') or 0)}",
        f"정답: {int(context.get('correct_count') or 0)}/{int(context.get('total_questions') or 0)}",
        f"소요시간(초): {int(context.get('duration_sec') or 0)}",
        f"오답수: {len(wrong_items)}",
        "과목별 통계:",
    ]
    if isinstance(subject_stats, dict):
        for subject_name, stat in subject_stats.items():
            total = int((stat or {}).get("total") or 0)
            correct = int((stat or {}).get("correct") or 0)
            acc = int(round((correct / max(1, total)) * 100))
            lines.append(f"- {subject_name}: {correct}/{total} ({acc}%)")

    lines.append("오답 문항 요약:")
    for item in wrong_items[:40]:
        lines.append(
            "- "
            f"{int(item.get('exam_index') or 0)}번 | {str(item.get('subject') or '')} | "
            f"내선택 {item.get('selected_index') or '미응답'} | 정답 {item.get('correct_index') or '-'} | "
            f"개념 {str(item.get('ontology_concept') or item.get('ontology_chapter') or '없음')}"
        )

    if focused:
        lines.append("사용자가 직접 지정한 문항 상세:")
        for item in focused:
            options = item.get("options") or []
            option_text = " | ".join(f"{idx + 1}) {str(opt)}" for idx, opt in enumerate(options[:4]))
            lines.append(
                "- "
                f"{int(item.get('exam_index') or 0)}번 문제: {str(item.get('question') or '')}\n"
                f"  보기: {option_text}\n"
                f"  내선택 {item.get('selected_index') or '미응답'} / 정답 {item.get('correct_index') or '-'}"
            )

    return "\n".join(lines)


def _build_mock_exam_leg_reply(context: Dict[str, Any], payload_raw: str, history: List[Dict[str, str]]) -> str:
    history_lines: List[str] = []
    for message in history[-6:]:
        role = str(message.get("role", "user") or "user").strip()
        content = str(message.get("content", "") or "").strip()
        if content:
            history_lines.append(f"[{role}] {content[:700]}")
    history_text = "\n".join(history_lines) if history_lines else "-"
    context_text = _build_mock_exam_context_for_leg(context, payload_raw)

    prompt = (
        "당신은 네트워크관리사 2급 모의고사 전용 코치입니다.\n"
        "사용자 질문을 그대로 해결하세요. 질문이 특정 요청이면 그 요청부터 답하고, 필요할 때만 요약을 덧붙이세요.\n"
        "항상 한국어로 답하세요.\n"
        "같은 개요 문장을 반복하지 마세요.\n"
        "사용자가 '중복/빈출 개념 정리'를 묻는 경우, 개념별 빈도와 해당 문항 번호를 우선 정리하세요.\n"
        "사용자가 여러 요구(예: 해설 + 유사문제)를 한 번에 말하면 둘 다 답하세요.\n"
        "모르는 내용은 추측하지 말고 현재 모의고사 정보 범위에서 답하세요.\n\n"
        f"[이전 대화]\n{history_text}\n\n"
        f"[모의고사 컨텍스트]\n{context_text}\n\n"
        f"[사용자 질문]\n{payload_raw}\n"
    )

    llm = ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_HOST,
        temperature=0,
        num_predict=min(settings.OLLAMA_SOLVE_NUM_PREDICT, 1800),
    )
    reply = str(llm.invoke(prompt, think=False).content or "").strip()
    return reply


def _build_mock_exam_overview(context: Dict[str, Any]) -> str:
    score = int(context.get("score") or 0)
    correct_count = int(context.get("correct_count") or 0)
    total_questions = int(context.get("total_questions") or 0)
    duration_sec = int(context.get("duration_sec") or 0)
    subject_stats = context.get("subject_stats") or {}

    ranked = []
    if isinstance(subject_stats, dict):
        for subject_name, stat in subject_stats.items():
            total = int((stat or {}).get("total") or 0)
            correct = int((stat or {}).get("correct") or 0)
            accuracy = int(round((correct / max(1, total)) * 100))
            ranked.append((str(subject_name), correct, total, accuracy))
    ranked.sort(key=lambda item: (item[3], item[0]))

    lines = [
        f"이번 모의고사 점수는 {score}점이고, 전체 {total_questions}문제 중 {correct_count}문제를 맞혔어요.",
        f"소요 시간은 {duration_sec}초였고, 취약 과목부터 보면 {', '.join(f'{subject} {accuracy}%' for subject, _, _, accuracy in ranked[:3]) or '데이터 없음'} 순서예요.",
    ]
    wrong_items = _mock_wrong_questions(context)
    if wrong_items:
        numbers = ", ".join(f"{int(item.get('exam_index') or 0)}번" for item in wrong_items[:8])
        lines.append(f"틀린 문제는 현재 {len(wrong_items)}개고, 대표적으로 {numbers} 같은 문항들이 있어요.")
    lines.append("원하면 '몇 번 문제 분석해줘', '몇 번 몇 번 틀렸어?', '1과목에서 틀린 개념만 뽑아줘'처럼 바로 이어서 질문하면 됩니다.")
    return "\n".join(lines)


def _mock_top_concepts(context: Dict[str, Any], limit: int = 5) -> List[str]:
    counts: Dict[str, int] = {}
    for item in _mock_wrong_questions(context):
        key = str(item.get("ontology_concept") or item.get("ontology_chapter") or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _ in ranked[: max(1, limit)]]


def _mock_find_questions_by_term(context: Dict[str, Any], term: str) -> List[Dict[str, Any]]:
    nterm = _normalize_lookup_text(term).replace(" ", "")
    if not nterm:
        return []
    matches: List[Dict[str, Any]] = []
    for item in _mock_context_questions(context):
        haystack = " ".join(
            [
                str(item.get("question") or ""),
                str(item.get("subject") or ""),
                str(item.get("ontology_subject") or ""),
                str(item.get("ontology_chapter") or ""),
                str(item.get("ontology_concept") or ""),
            ]
        )
        nhay = _normalize_lookup_text(haystack).replace(" ", "")
        if nterm in nhay:
            matches.append(item)
    return matches


def _extract_mock_related_search_hint(payload_raw: str) -> str:
    text = str(payload_raw or "")
    if not text:
        return ""
    acronym_match = re.search(r"\b[A-Z]{2,}(?:/[A-Z0-9]{2,})*\b", text)
    if acronym_match:
        return str(acronym_match.group(0)).strip()
    tokens = [token.strip() for token in re.split(r"[^0-9A-Za-z가-힣]+", text) if token.strip()]
    for token in tokens:
        if token in {"모의고사", "문제", "관련", "유사문제", "찾아줘", "찾아", "뽑아줘", "보여줘", "개념", "설명", "해설", "확인"}:
            continue
        if len(token) >= 2:
            return token
    return ""


async def _handle_mock_exam_analysis(payload_raw: str, history: List[Dict[str, str]], analysis: Any | None = None) -> Optional[Dict[str, Any]]:
    context = _extract_mock_exam_context(payload_raw, history)
    if not context:
        return None

    sequence = _analysis_intent_sequence(analysis) if analysis is not None else []
    has_mock_stage = (analysis is None) or ("MOCK_EXAM_ANALYZE" in sequence)
    if not has_mock_stage:
        return None

    analysis_keywords = (
        "오답",
        "틀린",
        "몇 번",
        "문항",
        "과목",
        "정답률",
        "취약",
        "빈출",
        "중복",
        "반복",
        "개념",
        "패턴",
        "점수",
        "분석",
        "학습",
        "우선순위",
    )
    normalized = _normalize_lookup_text(payload_raw)
    wants_analysis = (analysis is not None and str(getattr(analysis, "intent", "") or "") == "MOCK_EXAM_ANALYZE") or any(
        keyword in payload_raw or keyword in normalized for keyword in analysis_keywords
    )
    if not wants_analysis:
        return None

    numbered_leg = _build_mock_numbered_leg_reply(context, payload_raw)
    if numbered_leg is not None:
        numbered_leg["mock_summary"] = {
            "wrong_count": len(_mock_wrong_questions(context)),
            "top_concepts": _mock_top_concepts(context, limit=5),
        }
        return numbered_leg

    concept_candidate = ""
    tokens = [token for token in re.split(r"[^0-9A-Za-z가-힣]+", payload_raw) if token.strip()]
    for token in tokens:
        cleaned = token.strip()
        if cleaned in {"혹시", "지금", "푼", "모의고사", "문제", "관련", "있었나", "있었어", "있나", "문항", "개념", "중에", "중", "이", "그", "나", "도"}:
            continue
        if len(cleaned) >= 2:
            concept_candidate = cleaned
            break

    if concept_candidate and any(keyword in normalized for keyword in ("관련", "있었", "있나", "나왔", "문제")):
        matches = _mock_find_questions_by_term(context, concept_candidate)
        if matches:
            lines = [f"{concept_candidate} 관련 문항이 {len(matches)}개 있었어요."]
            for item in matches[:10]:
                lines.append(
                    f"- {int(item.get('exam_index') or 0)}번: {str(item.get('subject') or '')} / {str(item.get('question') or '')[:70]}"
                )
            lines.append("원하면 이 개념을 기준으로 바로 개념 해설도 이어갈 수 있어요.")
            return {
                "ok": True,
                "assistant_message": "\n".join(lines),
                "route": "mock-exam>term-lookup",
                "mock_summary": {
                    "wrong_count": len(_mock_wrong_questions(context)),
                    "top_concepts": _mock_top_concepts(context, limit=5),
                },
            }

    leg_reply = _build_mock_exam_leg_reply(context, payload_raw, history)
    if not leg_reply:
        leg_reply = _build_mock_exam_overview(context)

    wants_related_questions = any(keyword in normalized for keyword in ("관련", "유사문제", "문제은행", "문제", "뽑아", "찾아", "추천"))
    if wants_related_questions:
        search_hint = _extract_mock_related_search_hint(payload_raw)
        if not search_hint:
            top_concepts = _mock_top_concepts(context, limit=5)
            search_hint = top_concepts[0] if top_concepts else ""
        if search_hint:
            search_analysis = SimpleNamespace(
                intent="QUESTION_SEARCH",
                coordinate=SimpleNamespace(subject="", chapter="", concept=search_hint),
                coordinates=[],
                entities=[search_hint],
                search_query=search_hint,
            )
            questions = await _find_related_questions(
                payload=payload_raw,
                analysis=search_analysis,
                limit=_extract_requested_question_count(payload_raw),
            )
            if questions:
                search_reply = _format_question_search_reply(questions, search_analysis)
                out = {
                    "ok": True,
                    "assistant_message": f"{leg_reply}\n\n{search_reply}",
                    "route": "mock-exam>leg+db>question-search",
                    "mock_summary": {
                        "wrong_count": len(_mock_wrong_questions(context)),
                        "top_concepts": _mock_top_concepts(context, limit=5),
                    },
                    "recommended_questions": questions,
                }
                if analysis is not None and "CONCEPT_EXPLAIN" in sequence:
                    out["route"] = "mock-exam>leg+concept-leg+db>question-search"
                return out

    out: Dict[str, Any] = {
        "ok": True,
        "assistant_message": leg_reply,
        "route": "mock-exam>leg",
        "mock_summary": {
            "wrong_count": len(_mock_wrong_questions(context)),
            "top_concepts": _mock_top_concepts(context, limit=5),
        },
    }

    if analysis is not None and "CONCEPT_EXPLAIN" in sequence:
        top_concepts = _mock_top_concepts(context, limit=5)
        concept_hint = ", ".join(top_concepts) if top_concepts else "취약 개념"
        concept_payload = (
            f"{payload_raw}\n\n"
            f"[모의고사 분석 결과 핵심 개념]\n{concept_hint}\n"
            "위 핵심 개념을 초보자 눈높이로 핵심 원리와 헷갈리는 포인트 중심으로 설명해줘."
        )
        concept_history = [*history, {"role": "assistant", "content": leg_reply}]
        concept_analysis = SimpleNamespace(
            intent="CONCEPT_EXPLAIN",
            coordinate=getattr(analysis, "coordinate", None),
            coordinates=getattr(analysis, "coordinates", []),
            entities=getattr(analysis, "entities", []),
            search_query=(str(getattr(analysis, "search_query", "") or "").strip() or concept_hint),
        )
        try:
            report, evidence, concept_message = _build_concept_explain_leg_reply(
                payload=concept_payload,
                history=concept_history,
                analysis=concept_analysis,
            )
            out["leg"] = {
                "report": report,
                "evidence": [item.model_dump() for item in evidence],
            }
            out["assistant_message"] = f"{leg_reply}\n\n[개념 해설]\n{concept_message}"
            out["route"] = "mock-exam>leg+concept-leg"
        except Exception:
            try:
                concept_message, evidence = _build_general_rag_reply(
                    payload=concept_payload,
                    history=concept_history,
                    analysis=concept_analysis,
                )
                out["assistant_message"] = f"{leg_reply}\n\n[개념 해설]\n{concept_message}"
                out["rag"] = {"evidence": [item.model_dump() for item in evidence]}
                out["route"] = "mock-exam>leg+concept-rag"
            except Exception:
                out["route"] = "mock-exam>leg+concept-pending"

    return out


async def _ensure_chat_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forge_chat_conversations (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS forge_chat_conversations_username_updated_idx
        ON forge_chat_conversations(username, updated_at DESC)
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forge_chat_conversation_shares (
            share_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES forge_chat_conversations(id) ON DELETE CASCADE,
            owner_username TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS forge_chat_conversation_shares_conv_idx
        ON forge_chat_conversation_shares(conversation_id)
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forge_chat_conversation_user_state (
            username TEXT NOT NULL,
            conversation_id TEXT NOT NULL REFERENCES forge_chat_conversations(id) ON DELETE CASCADE,
            hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (username, conversation_id)
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS forge_chat_conversation_user_state_username_hidden_idx
        ON forge_chat_conversation_user_state(username, hidden_at DESC)
        """
    )


@app.get("/api/chat/conversations")
async def chat_list_conversations(request: Request, username: str = "", lite: int = 0):
    actor = _safe_username_from_header(request)
    target = str(username or actor).strip()
    if target != actor:
        raise HTTPException(status_code=403, detail="Cannot read another user's conversations.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        if int(lite or 0) == 1:
            rows = await conn.fetch(
                """
                            SELECT c.id, c.title, c.created_at, c.updated_at
                            FROM forge_chat_conversations c
                            LEFT JOIN forge_chat_conversation_user_state s
                                ON s.conversation_id = c.id AND s.username = $1
                            WHERE c.username = $1
                                AND s.conversation_id IS NULL
                            ORDER BY c.updated_at DESC
                """,
                actor,
            )
            conversations = [
                {
                    "id": str(row["id"]),
                    "title": str(row["title"] or "").strip() or "New Chat",
                    "createdAt": row["created_at"].isoformat() if row["created_at"] else "",
                    "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else "",
                    "messages": [],
                    "isHydrated": False,
                }
                for row in rows
            ]
            return {"ok": True, "conversations": conversations, "lite": True}

        rows = await conn.fetch(
            """
                        SELECT c.id, c.payload
                        FROM forge_chat_conversations c
                        LEFT JOIN forge_chat_conversation_user_state s
                            ON s.conversation_id = c.id AND s.username = $1
                        WHERE c.username = $1
                            AND s.conversation_id IS NULL
                        ORDER BY c.updated_at DESC
            """,
            actor,
        )
        conversations = [_coerce_json_object(row["payload"]) for row in rows]
        conversations = [item for item in conversations if item]
        return {"ok": True, "conversations": conversations, "lite": False}
    finally:
        await conn.close()


@app.get("/api/chat/conversations/{conversation_id}")
async def chat_get_conversation(conversation_id: str, request: Request):
    actor = _safe_username_from_header(request)
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        row = await conn.fetchrow(
            """
            SELECT c.payload
            FROM forge_chat_conversations c
            LEFT JOIN forge_chat_conversation_user_state s
                ON s.conversation_id = c.id AND s.username = $1
            WHERE c.id = $2
                AND c.username = $1
                AND s.conversation_id IS NULL
            LIMIT 1
            """,
            actor,
            conv_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conversation = _coerce_json_object(row["payload"])
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation payload is missing.")
        return {"ok": True, "conversation": conversation}
    finally:
        await conn.close()


@app.post("/api/chat/sync")
async def chat_sync_conversations(request: Request, body: ChatSyncRequest):
    actor = _safe_username_from_header(request)
    username = str(body.username or "").strip()
    if not username or username != actor:
        raise HTTPException(status_code=403, detail="Cannot sync another user's conversations.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        async with conn.transaction():
            for conv in body.conversations or []:
                conv_id = str(conv.get("id", "") or "").strip()
                title = str(conv.get("title", "") or "").strip() or "New Chat"
                if not conv_id:
                    continue
                await conn.execute(
                    """
                    INSERT INTO forge_chat_conversations (id, username, title, payload, created_at, updated_at)
                    VALUES ($1, $2, $3, $4::jsonb, NOW(), NOW())
                    ON CONFLICT (id)
                    DO UPDATE SET
                        username = EXCLUDED.username,
                        title = EXCLUDED.title,
                        payload = EXCLUDED.payload,
                        updated_at = NOW()
                    """,
                    conv_id,
                    actor,
                    title,
                    json.dumps(conv, ensure_ascii=False),
                )
        return {"ok": True, "count": len(body.conversations or [])}
    finally:
        await conn.close()


@app.post("/api/chat/conversations/{conversation_id}/hide")
async def chat_hide_conversation(conversation_id: str, request: Request):
    actor = _safe_username_from_header(request)
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        row = await conn.fetchrow(
            "SELECT id FROM forge_chat_conversations WHERE id = $1 AND username = $2 LIMIT 1",
            conv_id,
            actor,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        await conn.execute(
            """
            INSERT INTO forge_chat_conversation_user_state (username, conversation_id, hidden_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (username, conversation_id)
            DO UPDATE SET hidden_at = NOW()
            """,
            actor,
            conv_id,
        )
        return {"ok": True, "hiddenId": conv_id}
    finally:
        await conn.close()


@app.post("/api/chat/conversations/{conversation_id}/share")
async def chat_share_conversation(conversation_id: str, request: Request):
    actor = _safe_username_from_header(request)
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        row = await conn.fetchrow(
            "SELECT id FROM forge_chat_conversations WHERE id = $1 AND username = $2",
            conv_id,
            actor,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        existing = await conn.fetchrow(
            "SELECT share_id FROM forge_chat_conversation_shares WHERE conversation_id = $1 AND owner_username = $2 LIMIT 1",
            conv_id,
            actor,
        )
        if existing and existing["share_id"]:
            share_id = str(existing["share_id"])
        else:
            share_id = secrets.token_urlsafe(10)
            await conn.execute(
                "INSERT INTO forge_chat_conversation_shares (share_id, conversation_id, owner_username) VALUES ($1, $2, $3)",
                share_id,
                conv_id,
                actor,
            )
        return {"ok": True, "shareId": share_id}
    finally:
        await conn.close()


@app.get("/api/chat/shared/{share_id}")
async def chat_get_shared_conversation(share_id: str):
    share_key = str(share_id or "").strip()
    if not share_key:
        raise HTTPException(status_code=400, detail="share_id is required.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        row = await conn.fetchrow(
            """
            SELECT c.payload, s.share_id, s.owner_username, s.created_at
            FROM forge_chat_conversation_shares s
            JOIN forge_chat_conversations c ON c.id = s.conversation_id
            WHERE s.share_id = $1
            LIMIT 1
            """,
            share_key,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Shared conversation not found.")
        conversation = _coerce_json_object(row["payload"])
        if not conversation:
            raise HTTPException(status_code=404, detail="Shared conversation payload is missing.")
        return {
            "ok": True,
            "shareId": row["share_id"],
            "owner": row["owner_username"],
            "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
            "conversation": conversation,
        }
    finally:
        await conn.close()


@app.get("/api/questions/bank")
async def list_question_bank(
    request: Request,
    subject: str = "",
    q: str = "",
    limit: int = 20,
    offset: int = 0,
):
    _safe_username_from_header(request)
    safe_limit = min(max(int(limit or 20), 1), 100)
    safe_offset = min(max(int(offset or 0), 0), 500_000)
    subject_filter = str(subject or "").strip()
    search = str(q or "").strip()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        where_parts: List[str] = []
        params: List[Any] = []

        if subject_filter:
            params.append(subject_filter)
            where_parts.append(f"subject ILIKE ${len(params)} || '%' ")

        relevance_sql = "0.0"
        if search:
            params.append(search)
            q_idx = len(params)
            relevance_sql = (
                "GREATEST("
                f"COALESCE(similarity(question, ${q_idx}), 0),"
                f"COALESCE(similarity(option1 || ' ' || option2 || ' ' || option3 || ' ' || option4, ${q_idx}), 0),"
                f"COALESCE(similarity(COALESCE(ontology_concept, ''), ${q_idx}), 0)"
                ")"
            )
            where_parts.append(
                "("
                f"question ILIKE '%' || ${q_idx} || '%' OR "
                f"option1 ILIKE '%' || ${q_idx} || '%' OR "
                f"option2 ILIKE '%' || ${q_idx} || '%' OR "
                f"option3 ILIKE '%' || ${q_idx} || '%' OR "
                f"option4 ILIKE '%' || ${q_idx} || '%' OR "
                f"COALESCE(ontology_concept, '') ILIKE '%' || ${q_idx} || '%' OR "
                f"similarity(question, ${q_idx}) > 0.1 OR "
                f"similarity(option1 || ' ' || option2 || ' ' || option3 || ' ' || option4, ${q_idx}) > 0.1"
                ")"
            )

        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) AS cnt FROM questions {where_sql}",
            *params,
        )

        params_for_rows = params + [safe_limit, safe_offset]
        rows = await conn.fetch(
            f"""
            SELECT id, subject, question, option1, option2, option3, option4, answer,
                   ontology_subject, ontology_chapter, ontology_concept,
                   {relevance_sql} AS relevance
            FROM questions
            {where_sql}
            ORDER BY relevance DESC, id DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """,
            *params_for_rows,
        )

        question_items = [
            {
                "id": int(row["id"]),
                "subject": str(row["subject"]),
                "question": str(row["question"]),
                "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
                "answer": int(row["answer"]),
                "ontology_subject": str(row.get("ontology_subject") or ""),
                "ontology_chapter": str(row.get("ontology_chapter") or ""),
                "ontology_concept": str(row.get("ontology_concept") or ""),
                "relevance": float(row["relevance"] or 0),
            }
            for row in rows
        ]

        return {
            "ok": True,
            "total": int(total_row["cnt"] if total_row else 0),
            "limit": safe_limit,
            "offset": safe_offset,
            "questions": question_items,
            "items": question_items,
        }
    finally:
        await conn.close()


@app.get("/api/questions/{question_id}")
async def get_question_bank_item(request: Request, question_id: int):
    _safe_username_from_header(request)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, subject, question, option1, option2, option3, option4, answer,
                   ontology_subject, ontology_chapter, ontology_concept
            FROM questions
            WHERE id = $1
            LIMIT 1
            """,
            int(question_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Question not found.")
        return {
            "ok": True,
            "question": {
                "id": int(row["id"]),
                "subject": str(row["subject"]),
                "question": str(row["question"]),
                "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
                "answer": int(row["answer"]),
                "ontology_subject": str(row.get("ontology_subject") or ""),
                "ontology_chapter": str(row.get("ontology_chapter") or ""),
                "ontology_concept": str(row.get("ontology_concept") or ""),
            },
        }
    finally:
        await conn.close()


@app.post("/api/mock-exams/generate")
async def generate_mock_exam(request: Request, body: MockExamGenerateRequest):
    _safe_username_from_header(request)
    subject_counts = _normalize_subject_counts(body.subject_counts)
    seed = body.seed
    rng = random.Random(seed) if seed is not None else random.Random()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        selected_rows: List[asyncpg.Record] = []
        for subject, needed_count in subject_counts.items():
            rows = await conn.fetch(
                """
                SELECT id, subject, question, option1, option2, option3, option4, answer
                FROM questions
                WHERE subject ILIKE $1 || '%'
                """,
                subject,
            )
            if len(rows) < needed_count:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough questions for {subject}: required={needed_count}, available={len(rows)}",
                )
            selected_rows.extend(rng.sample(list(rows), needed_count))

        rng.shuffle(selected_rows)
        quiz_uid = secrets.token_urlsafe(12)

        return {
            "ok": True,
            "quiz_uid": quiz_uid,
            "subject_counts": subject_counts,
            "total_questions": len(selected_rows),
            "questions": [
                {
                    "id": int(row["id"]),
                    "subject": str(row["subject"]),
                    "question": str(row["question"]),
                    "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
                }
                for row in selected_rows
            ],
        }
    finally:
        await conn.close()


@app.post("/api/mock-exams/submit")
async def submit_mock_exam(request: Request, body: MockExamSubmitRequest):
    actor = _safe_username_from_header(request)
    quiz_uid = str(body.quiz_uid or "").strip()
    if not quiz_uid:
        raise HTTPException(status_code=400, detail="quiz_uid is required.")
    if not body.answers:
        raise HTTPException(status_code=400, detail="answers is required.")

    answer_map: Dict[int, Optional[int]] = {}
    for item in body.answers:
        qid = int(item.question_id)
        sel = item.selected_index
        if sel is not None and (int(sel) < 1 or int(sel) > 4):
            raise HTTPException(status_code=400, detail="selected_index must be 1..4.")
        answer_map[qid] = int(sel) if sel is not None else None

    question_ids = list(answer_map.keys())
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            """
            SELECT id, subject, question, answer,
                   option1, option2, option3, option4,
                   ontology_subject, ontology_chapter, ontology_concept
            FROM questions
            WHERE id = ANY($1::bigint[])
            """,
            question_ids,
        )
        by_id: Dict[int, asyncpg.Record] = {int(row["id"]): row for row in rows}
        if len(by_id) != len(question_ids):
            missing = [qid for qid in question_ids if qid not in by_id]
            raise HTTPException(status_code=400, detail=f"Unknown question ids: {missing[:5]}")

        result_rows: List[Dict[str, Any]] = []
        subject_stats: Dict[str, Dict[str, int]] = {}
        correct_count = 0

        for qid in question_ids:
            row = by_id[qid]
            subject = str(row["subject"])
            correct = int(row["answer"])
            selected = answer_map[qid]
            is_correct = selected == correct
            if is_correct:
                correct_count += 1

            if subject not in subject_stats:
                subject_stats[subject] = {"total": 0, "correct": 0}
            subject_stats[subject]["total"] += 1
            if is_correct:
                subject_stats[subject]["correct"] += 1

            result_rows.append(
                {
                    "exam_index": len(result_rows) + 1,
                    "question_id": qid,
                    "subject": subject,
                    "question": str(row["question"]),
                    "options": [str(row["option1"]), str(row["option2"]), str(row["option3"]), str(row["option4"])],
                    "selected_index": selected,
                    "correct_index": correct,
                    "is_correct": is_correct,
                    "ontology_subject": str(row.get("ontology_subject") or ""),
                    "ontology_chapter": str(row.get("ontology_chapter") or ""),
                    "ontology_concept": str(row.get("ontology_concept") or ""),
                }
            )

        total_questions = len(result_rows)
        score = int(round((correct_count / max(1, total_questions)) * 100))

        # user_id가 있을 때만 quiz_attempts에 영속 저장 (local-only 사용자와 호환)
        attempt_id: Optional[int] = None
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1",
            actor,
        )
        if user_row and user_row.get("id") is not None:
            async with conn.transaction():
                inserted = await conn.fetchrow(
                    """
                    INSERT INTO quiz_attempts (user_id, total_questions, correct_count, score, duration_sec, quiz_uid)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    int(user_row["id"]),
                    total_questions,
                    correct_count,
                    score,
                    max(0, int(body.duration_sec or 0)),
                    quiz_uid,
                )
                attempt_id = int(inserted["id"])
                for row in result_rows:
                    await conn.execute(
                        """
                        INSERT INTO quiz_attempt_answers (
                            attempt_id, question_id, subject, question_text,
                            selected_index, correct_index, is_correct
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        attempt_id,
                        int(row["question_id"]),
                        str(row["subject"]),
                        str(row["question"]),
                        row["selected_index"],
                        int(row["correct_index"]),
                        bool(row["is_correct"]),
                    )

        wrong_questions = [
            {
                "question_id": int(row["question_id"]),
                "subject": str(row["subject"]),
                "question": str(row["question"]),
                "selected_index": row["selected_index"],
                "correct_index": int(row["correct_index"]),
            }
            for row in result_rows
            if not row["is_correct"]
        ]

        return {
            "ok": True,
            "quiz_uid": quiz_uid,
            "attempt_id": attempt_id,
            "persisted": bool(attempt_id),
            "total_questions": total_questions,
            "correct_count": correct_count,
            "score": score,
            "duration_sec": max(0, int(body.duration_sec or 0)),
            "subject_stats": subject_stats,
            "answer_details": result_rows,
            "wrong_questions": wrong_questions,
            "chat_followup": _mock_exam_chat_followup(result_rows, subject_stats),
        }
    finally:
        await conn.close()


@app.get("/api/mock-exams/history")
async def list_mock_exam_history(request: Request, limit: int = 20, offset: int = 0):
    actor = _safe_username_from_header(request)
    safe_limit = min(max(int(limit or 20), 1), 100)
    safe_offset = min(max(int(offset or 0), 0), 500_000)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1",
            actor,
        )
        if not user_row or user_row.get("id") is None:
            return {"ok": True, "total": 0, "attempts": []}

        user_id = int(user_row["id"])
        rows = await conn.fetch(
            """
            SELECT id, quiz_uid, total_questions, correct_count, score, duration_sec, created_at
            FROM quiz_attempts
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id,
            safe_limit,
            safe_offset,
        )
        total_row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM quiz_attempts WHERE user_id = $1",
            user_id,
        )

        return {
            "ok": True,
            "total": int(total_row["cnt"] if total_row else 0),
            "attempts": [
                {
                    "attempt_id": int(row["id"]),
                    "quiz_uid": str(row["quiz_uid"] or ""),
                    "total_questions": int(row["total_questions"] or 0),
                    "correct_count": int(row["correct_count"] or 0),
                    "wrong_count": max(0, int(row["total_questions"] or 0) - int(row["correct_count"] or 0)),
                    "score": int(row["score"] or 0),
                    "duration_sec": int(row["duration_sec"] or 0),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in rows
            ],
        }
    finally:
        await conn.close()


@app.get("/api/mock-exams/history/{attempt_id}")
async def get_mock_exam_history_detail(request: Request, attempt_id: int):
    actor = _safe_username_from_header(request)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1",
            actor,
        )
        if not user_row or user_row.get("id") is None:
            raise HTTPException(status_code=404, detail="Mock exam history not found.")

        attempt_row = await conn.fetchrow(
            """
            SELECT id, quiz_uid, total_questions, correct_count, score, duration_sec, created_at
            FROM quiz_attempts
            WHERE id = $1 AND user_id = $2
            LIMIT 1
            """,
            int(attempt_id),
            int(user_row["id"]),
        )
        if not attempt_row:
            raise HTTPException(status_code=404, detail="Mock exam history not found.")

        answer_rows = await conn.fetch(
            """
            SELECT a.question_id, a.subject, a.question_text, a.selected_index, a.correct_index, a.is_correct,
                   q.option1, q.option2, q.option3, q.option4,
                   q.ontology_subject, q.ontology_chapter, q.ontology_concept
            FROM quiz_attempt_answers a
            LEFT JOIN questions q ON q.id = a.question_id
            WHERE attempt_id = $1
            ORDER BY a.id
            """,
            int(attempt_id),
        )

        subject_stats: Dict[str, Dict[str, int]] = {}
        answers: List[Dict[str, Any]] = []
        for row in answer_rows:
            subject = str(row["subject"] or "")
            if subject not in subject_stats:
                subject_stats[subject] = {"total": 0, "correct": 0}
            subject_stats[subject]["total"] += 1
            if bool(row["is_correct"]):
                subject_stats[subject]["correct"] += 1

            answers.append(
                {
                    "exam_index": len(answers) + 1,
                    "question_id": int(row["question_id"] or 0),
                    "subject": subject,
                    "question": str(row["question_text"] or ""),
                    "options": [
                        str(row.get("option1") or ""),
                        str(row.get("option2") or ""),
                        str(row.get("option3") or ""),
                        str(row.get("option4") or ""),
                    ],
                    "selected_index": int(row["selected_index"]) if row["selected_index"] is not None else None,
                    "correct_index": int(row["correct_index"] or 0),
                    "is_correct": bool(row["is_correct"]),
                    "ontology_subject": str(row.get("ontology_subject") or ""),
                    "ontology_chapter": str(row.get("ontology_chapter") or ""),
                    "ontology_concept": str(row.get("ontology_concept") or ""),
                }
            )

        result_rows = [
            {
                "question_id": item["question_id"],
                "subject": item["subject"],
                "question": item["question"],
                "selected_index": item["selected_index"],
                "correct_index": item["correct_index"],
                "is_correct": item["is_correct"],
            }
            for item in answers
        ]

        return {
            "ok": True,
            "attempt": {
                "attempt_id": int(attempt_row["id"]),
                "quiz_uid": str(attempt_row["quiz_uid"] or ""),
                "total_questions": int(attempt_row["total_questions"] or 0),
                "correct_count": int(attempt_row["correct_count"] or 0),
                "wrong_count": max(0, int(attempt_row["total_questions"] or 0) - int(attempt_row["correct_count"] or 0)),
                "score": int(attempt_row["score"] or 0),
                "duration_sec": int(attempt_row["duration_sec"] or 0),
                "created_at": attempt_row["created_at"].isoformat() if attempt_row["created_at"] else None,
                "subject_stats": subject_stats,
                "all_questions": answers,
                "wrong_questions": [item for item in answers if not item["is_correct"]],
                "correct_questions": [item for item in answers if item["is_correct"]],
                "chat_followup": _mock_exam_chat_followup(result_rows, subject_stats),
                "answers": answers,
            },
        }
    finally:
        await conn.close()


@app.delete("/api/mock-exams/history/{attempt_id}")
async def delete_mock_exam_history(request: Request, attempt_id: int):
    actor = _safe_username_from_header(request)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        user_row = await conn.fetchrow(
            "SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1",
            actor,
        )
        if not user_row or user_row.get("id") is None:
            raise HTTPException(status_code=404, detail="Mock exam history not found.")

        owned_row = await conn.fetchrow(
            "SELECT id FROM quiz_attempts WHERE id = $1 AND user_id = $2 LIMIT 1",
            int(attempt_id),
            int(user_row["id"]),
        )
        if not owned_row:
            raise HTTPException(status_code=404, detail="Mock exam history not found.")

        async with conn.transaction():
            await conn.execute("DELETE FROM rag_solve_jobs WHERE quiz_attempt_id = $1", int(attempt_id))
            await conn.execute("DELETE FROM quiz_attempt_answers WHERE attempt_id = $1", int(attempt_id))
            await conn.execute("DELETE FROM quiz_attempts WHERE id = $1", int(attempt_id))

        return {"ok": True, "deletedId": int(attempt_id)}
    finally:
        await conn.close()


# ─────────────────────────────────────────────
# Admin API (로그인 세션 기반 인증)
# ─────────────────────────────────────────────
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def _fetch_node_session_user(cookie_header: str) -> Optional[dict]:
    """Node auth(/api/auth/me)로 현재 로그인 사용자를 조회합니다."""
    if not cookie_header:
        return None
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:3100/api/auth/me",
            headers={
                "Cookie": cookie_header,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
            user = payload.get("user") if isinstance(payload, dict) else None
            return user if isinstance(user, dict) else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None


async def _ensure_admin_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")
    await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_permissions JSONB")
    # deamon 계정은 항상 관리자 권한 보장
    await conn.execute("UPDATE users SET is_admin = TRUE WHERE lower(username) = 'deamon' AND is_admin = FALSE")


DEFAULT_ADMIN_PERMISSIONS = {
    "users": {"read": True, "write": True, "delete": True},
    "logs": {"read": True},
    "rag": {"read": True, "delete": True},
    "quiz": {"read": True, "delete": True},
    "questions": {"read": True},
    "conversations": {"read": True},
}


def _merge_admin_permissions(raw: Any, username: str) -> dict:
    """DB의 admin_permissions(JSON)와 기본값을 합칩니다. deamon은 항상 전체 허용."""
    if str(username or "").lower() == "deamon":
        return json.loads(json.dumps(DEFAULT_ADMIN_PERMISSIONS))
    out = {k: dict(v) for k, v in DEFAULT_ADMIN_PERMISSIONS.items()}
    if raw is None:
        return out
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return out
    if not isinstance(data, dict):
        return out
    for section, actions in data.items():
        if section not in out or not isinstance(actions, dict):
            continue
        for act, val in actions.items():
            if act in out[section]:
                out[section][act] = bool(val)
    return out


def _admin_perm_ok(perms: dict, section: str, action: str) -> bool:
    sec = perms.get(section) or {}
    return bool(sec.get(action, False))


async def _get_session_user_from_request(request: Request) -> Optional[dict]:
    header_user = str(request.headers.get("X-Session-User", "") or "").strip()
    if header_user:
        return {"id": None, "username": header_user}
    cookie_header = request.headers.get("cookie", "")
    loop = asyncio.get_running_loop()
    user = await loop.run_in_executor(None, lambda: _fetch_node_session_user(cookie_header))
    return user


async def _require_admin(request: Request) -> dict:
    # 비상용 토큰 유지(옵션) — 전체 관리자 권한
    token = request.headers.get("X-Admin-Token", "")
    if ADMIN_TOKEN and token and token == ADMIN_TOKEN:
        return {
            "id": None,
            "username": "token-admin",
            "isAdmin": True,
            "permissions": json.loads(json.dumps(DEFAULT_ADMIN_PERMISSIONS)),
        }

    session_user = await _get_session_user_from_request(request)
    if not session_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    header_username = str(session_user.get("username", "") or "").strip().lower()
    if header_username and header_username != "cortie":
        raise HTTPException(status_code=403, detail="관리자 페이지는 cortie 계정만 접근할 수 있습니다.")
    if header_username == "cortie":
        return {
            "id": session_user.get("id"),
            "username": "cortie",
            "isAdmin": True,
            "permissions": json.loads(json.dumps(DEFAULT_ADMIN_PERMISSIONS)),
        }

    user_id = session_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="세션 사용자 정보를 확인할 수 없습니다.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_admin_schema(conn)
        row = await conn.fetchrow(
            "SELECT id, username, email, name, student_number, is_admin, admin_permissions FROM users WHERE id = $1",
            int(user_id),
        )
        if not row:
            raise HTTPException(status_code=403, detail="사용자 정보를 찾을 수 없습니다.")

        username = str(row["username"] or "").lower()
        is_admin = bool(row["is_admin"]) and username == "cortie"

        if not is_admin:
            raise HTTPException(status_code=403, detail="관리자 페이지는 cortie 계정만 접근할 수 있습니다.")

        perms = _merge_admin_permissions(row["admin_permissions"], username)
        return {
            "id": int(row["id"]),
            "username": row["username"],
            "email": row["email"],
            "name": row["name"],
            "studentNumber": row["student_number"],
            "isAdmin": True,
            "permissions": perms,
        }
    finally:
        await conn.close()


async def _require_admin_perm(request: Request, section: str, action: str) -> dict:
    ctx = await _require_admin(request)
    if not _admin_perm_ok(ctx["permissions"], section, action):
        raise HTTPException(
            status_code=403,
            detail=f"'{section}' 영역의 '{action}' 권한이 없습니다.",
        )
    return ctx


@app.get("/api/admin/me")
async def admin_me(request: Request):
    session_user = await _get_session_user_from_request(request)
    if not session_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    header_username = str(session_user.get("username", "") or "").strip()
    if header_username:
        is_admin = header_username.lower() == "cortie"
        return {
            "ok": True,
            "user": {
                "id": session_user.get("id"),
                "username": header_username,
                "email": None,
                "name": None,
                "studentNumber": None,
                "isAdmin": is_admin,
                "permissions": json.loads(json.dumps(DEFAULT_ADMIN_PERMISSIONS)) if is_admin else None,
            },
        }

    user_id = session_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="세션 사용자 정보를 확인할 수 없습니다.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_admin_schema(conn)
        row = await conn.fetchrow(
            "SELECT id, username, email, name, student_number, is_admin, admin_permissions FROM users WHERE id = $1",
            int(user_id),
        )
        if not row:
            raise HTTPException(status_code=403, detail="사용자 정보를 찾을 수 없습니다.")

        username = str(row["username"] or "").lower()
        is_admin = bool(row["is_admin"]) or username == "deamon"
        if username == "deamon" and not bool(row["is_admin"]):
            await conn.execute("UPDATE users SET is_admin = TRUE WHERE id = $1", int(row["id"]))
            is_admin = True

        perms = _merge_admin_permissions(row["admin_permissions"], username) if is_admin else None

        return {
            "ok": True,
            "user": {
                "id": int(row["id"]),
                "username": row["username"],
                "email": row["email"],
                "name": row["name"],
                "studentNumber": row["student_number"],
                "isAdmin": bool(is_admin),
                "permissions": perms,
            },
        }
    finally:
        await conn.close()


# ── 사용자 목록 ──
@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    await _require_admin_perm(request, "users", "read")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_admin_schema(conn)
        rows = await conn.fetch(
            "SELECT id, email, username, name, student_number, is_admin, admin_permissions, created_at FROM users ORDER BY id"
        )
        return {"ok": True, "users": [
            {"id": r["id"], "email": r["email"], "username": r["username"],
             "name": r["name"], "studentNumber": r["student_number"],
             "isAdmin": bool(r["is_admin"]),
             "adminPermissions": r["admin_permissions"],
             "createdAt": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]}
    finally:
        await conn.close()


# ── 사용자 수정 ──
@app.patch("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request):
    await _require_admin_perm(request, "users", "write")
    body = await request.json()
    updates = []
    params = [user_id]

    if "username" in body and body["username"]:
        params.append(str(body["username"]).strip())
        updates.append(f"username = ${len(params)}")
    if "email" in body and body["email"]:
        params.append(str(body["email"]).strip())
        updates.append(f"email = ${len(params)}")
    if "name" in body and body["name"]:
        params.append(str(body["name"]).strip())
        updates.append(f"name = ${len(params)}")
    if "isAdmin" in body:
        params.append(bool(body["isAdmin"]))
        updates.append(f"is_admin = ${len(params)}")
    if "adminPermissions" in body or "admin_permissions" in body:
        raw_perm = body.get("adminPermissions", body.get("admin_permissions"))
        if raw_perm is None:
            updates.append("admin_permissions = NULL")
        else:
            if not isinstance(raw_perm, dict):
                raise HTTPException(status_code=400, detail="adminPermissions는 JSON 객체여야 합니다.")
            params.append(json.dumps(raw_perm, ensure_ascii=False))
            updates.append(f"admin_permissions = ${len(params)}::jsonb")
    if "password" in body and body["password"]:
        pw_hash = bcrypt.hashpw(str(body["password"]).encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        params.append(pw_hash)
        updates.append(f"password_hash = ${len(params)}")

    if not updates:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다.")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_admin_schema(conn)
        result = await conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = $1",
            *params
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        return {"ok": True}
    finally:
        await conn.close()


# ── 사용자 삭제 ──
@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, request: Request):
    await _require_admin_perm(request, "users", "delete")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM refresh_tokens WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM user_api_tokens WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM quiz_attempt_answers WHERE attempt_id IN (SELECT id FROM quiz_attempts WHERE user_id = $1)", user_id)
        await conn.execute("DELETE FROM quiz_attempts WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM rag_solve_jobs WHERE user_id = $1", user_id)
        result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        return {"ok": True}
    finally:
        await conn.close()


# ── API 로그 목록 ──
@app.get("/api/admin/logs")
async def admin_list_logs(request: Request, limit: int = 100, offset: int = 0, endpoint: str = ""):
    await _require_admin_perm(request, "logs", "read")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        safe_limit = min(max(int(limit or 20), 1), 100)
        safe_offset = max(int(offset or 0), 0)
        where = "WHERE endpoint ILIKE $3" if endpoint else ""
        params_count = [safe_limit, safe_offset, f"%{endpoint}%"] if endpoint else [safe_limit, safe_offset]
        rows = await conn.fetch(
            f"""SELECT id, endpoint, method, user_id, status_code, response_time_ms,
                       error_message, created_at
                FROM api_request_logs
                {where}
                ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
            *params_count
        )
        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) FROM api_request_logs {'WHERE endpoint ILIKE $1' if endpoint else ''}",
            *([ f"%{endpoint}%" ] if endpoint else [])
        )
        return {"ok": True, "total": total_row[0], "logs": [
            {"id": r["id"], "endpoint": r["endpoint"], "method": r["method"],
             "userId": r["user_id"], "statusCode": r["status_code"],
             "responseTimeMs": r["response_time_ms"],
             "errorMessage": r["error_message"],
             "createdAt": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]}
    finally:
        await conn.close()


@app.get("/api/admin/logs/{log_id}")
async def admin_get_log_detail(log_id: int, request: Request):
    await _require_admin_perm(request, "logs", "read")

    def _safe_payload(payload: Any, endpoint: str, max_chars: int = 120000):
        if payload is None:
            return None
        # 관리자 API 로그는 과거 재귀 적재로 매우 커질 수 있어 상세 payload는 생략
        if str(endpoint or "").startswith("/api/admin/"):
            return {
                "_omitted": True,
                "reason": "admin endpoint payload omitted to prevent recursive heavy rendering",
            }
        try:
            text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            return payload
        if len(text) <= max_chars:
            return payload
        return {
            "_truncated": True,
            "_originalChars": len(text),
            "_preview": text[:max_chars],
        }

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, endpoint, method, user_id, status_code, response_time_ms,
                   request_payload, response_payload, error_message, created_at
            FROM api_request_logs
            WHERE id = $1
            LIMIT 1
            """,
            log_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="로그를 찾을 수 없습니다.")

        return {
            "ok": True,
            "log": {
                "id": row["id"],
                "endpoint": row["endpoint"],
                "method": row["method"],
                "userId": row["user_id"],
                "statusCode": row["status_code"],
                "responseTimeMs": row["response_time_ms"],
                "requestPayload": _safe_payload(row["request_payload"], row["endpoint"]),
                "responsePayload": _safe_payload(row["response_payload"], row["endpoint"]),
                "errorMessage": row["error_message"],
                "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
            },
        }
    finally:
        await conn.close()


@app.get("/api/admin/conversations")
async def admin_list_conversations(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    username: str = "",
):
    await _require_admin_perm(request, "conversations", "read")
    safe_limit = min(max(int(limit or 20), 1), 200)
    safe_offset = max(int(offset or 0), 0)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        where = "WHERE username ILIKE $3" if username else ""
        params = [safe_limit, safe_offset, f"%{username}%"] if username else [safe_limit, safe_offset]
        rows = await conn.fetch(
            f"""
            SELECT id, username, title, payload, created_at, updated_at
            FROM forge_chat_conversations
            {where}
            ORDER BY updated_at DESC
            LIMIT $1 OFFSET $2
            """,
            *params,
        )
        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) FROM forge_chat_conversations {'WHERE username ILIKE $1' if username else ''}",
            *([f"%{username}%"] if username else []),
        )
        items = []
        for row in rows:
            payload = _coerce_json_object(row["payload"])
            messages = payload.get("messages") if isinstance(payload, dict) else []
            msg_count = len(messages) if isinstance(messages, list) else 0
            preview = ""
            if isinstance(messages, list):
                for message in reversed(messages):
                    if isinstance(message, dict) and str(message.get("content", "")).strip():
                        preview = str(message.get("content", "")).strip()[:140]
                        break
            items.append(
                {
                    "id": row["id"],
                    "username": row["username"],
                    "title": row["title"],
                    "messageCount": msg_count,
                    "preview": preview,
                    "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
                    "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
            )
        return {"ok": True, "total": total_row[0], "conversations": items}
    finally:
        await conn.close()


@app.get("/api/admin/conversations/{conversation_id}")
async def admin_get_conversation_detail(conversation_id: str, request: Request):
    await _require_admin_perm(request, "conversations", "read")
    conv_id = str(conversation_id or "").strip()
    if not conv_id:
        raise HTTPException(status_code=400, detail="conversation_id is required.")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        row = await conn.fetchrow(
            """
            SELECT id, username, title, payload, created_at, updated_at
            FROM forge_chat_conversations
            WHERE id = $1
            LIMIT 1
            """,
            conv_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="대화 내역을 찾을 수 없습니다.")
        return {
            "ok": True,
            "conversation": {
                "id": row["id"],
                "username": row["username"],
                "title": row["title"],
                "payload": _coerce_json_object(row["payload"]),
                "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
                "updatedAt": row["updated_at"].isoformat() if row["updated_at"] else None,
            },
        }
    finally:
        await conn.close()


# ── RAG Jobs (전체) ──
@app.get("/api/admin/rag-jobs")
async def admin_list_rag_jobs(request: Request, limit: int = 100, offset: int = 0):
    await _require_admin_perm(request, "rag", "read")
    safe_limit = min(max(int(limit or 20), 1), 500)
    safe_offset = min(max(int(offset or 0), 0), 500_000)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            """SELECT j.id, j.user_id, u.username, j.status, j.question_text,
                      j.wrong_choice, j.answer_choice, j.result_payload,
                      j.error_message, j.created_at, j.completed_at
               FROM rag_solve_jobs j
               LEFT JOIN users u ON u.id = j.user_id
               ORDER BY j.created_at DESC LIMIT $1 OFFSET $2""",
            safe_limit, safe_offset
        )
        total_row = await conn.fetchrow("SELECT COUNT(*) FROM rag_solve_jobs")
        return {"ok": True, "total": total_row[0], "jobs": [
            {"id": r["id"], "userId": r["user_id"], "username": r["username"],
             "status": r["status"], "questionText": r["question_text"],
             "wrongChoice": r["wrong_choice"], "answerChoice": r["answer_choice"],
             "resultPayload": r["result_payload"],
             "errorMessage": r["error_message"],
             "createdAt": r["created_at"].isoformat() if r["created_at"] else None,
             "completedAt": r["completed_at"].isoformat() if r["completed_at"] else None}
            for r in rows
        ]}
    finally:
        await conn.close()


@app.delete("/api/admin/rag-jobs/{job_id}")
async def admin_delete_rag_job(job_id: int, request: Request):
    await _require_admin_perm(request, "rag", "delete")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.execute("DELETE FROM rag_solve_jobs WHERE id = $1", job_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="해설 기록을 찾을 수 없습니다.")
        return {"ok": True, "deletedId": job_id}
    finally:
        await conn.close()


# ── 퀴즈 기록 (전체) ──
@app.get("/api/admin/quiz-attempts")
async def admin_list_quiz_attempts(request: Request, limit: int = 100, offset: int = 0):
    await _require_admin_perm(request, "quiz", "read")
    safe_limit = min(max(int(limit or 20), 1), 500)
    safe_offset = min(max(int(offset or 0), 0), 500_000)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            """SELECT a.id, a.user_id, u.username, a.total_questions, a.correct_count,
                      a.score, a.duration_sec, a.quiz_uid, a.created_at
               FROM quiz_attempts a
               LEFT JOIN users u ON u.id = a.user_id
               ORDER BY a.created_at DESC LIMIT $1 OFFSET $2""",
            safe_limit, safe_offset
        )
        total_row = await conn.fetchrow("SELECT COUNT(*) FROM quiz_attempts")
        return {"ok": True, "total": total_row[0], "attempts": [
            {"id": r["id"], "userId": r["user_id"], "username": r["username"],
             "totalQuestions": r["total_questions"], "correctCount": r["correct_count"],
             "score": r["score"], "durationSec": r["duration_sec"],
             "quizUid": r["quiz_uid"],
             "createdAt": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]}
    finally:
        await conn.close()


# ── 퀴즈 답안 상세 ──
@app.get("/api/admin/quiz-attempts/{attempt_id}/answers")
async def admin_get_attempt_answers(attempt_id: int, request: Request):
    await _require_admin_perm(request, "quiz", "read")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            """SELECT id, question_id, subject, question_text, selected_index, correct_index, is_correct
               FROM quiz_attempt_answers WHERE attempt_id = $1 ORDER BY id""",
            attempt_id
        )
        return {"ok": True, "answers": [
            {"id": r["id"], "questionId": r["question_id"], "subject": r["subject"],
             "questionText": r["question_text"], "selectedIndex": r["selected_index"],
             "correctIndex": r["correct_index"], "isCorrect": r["is_correct"]}
            for r in rows
        ]}
    finally:
        await conn.close()


@app.delete("/api/admin/quiz-attempts/{attempt_id}/rag-jobs")
async def admin_clear_attempt_rag_jobs(attempt_id: int, request: Request):
    """퀴즈 시도에 연결된 rag_solve_jobs만 삭제. 답안·시도 행은 유지 → 학습자가 퀴즈 상세에서 해설을 다시 신청 가능."""
    await _require_admin_perm(request, "rag", "delete")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow("SELECT id FROM quiz_attempts WHERE id = $1", attempt_id)
        if not row:
            raise HTTPException(status_code=404, detail="퀴즈 기록을 찾을 수 없습니다.")
        result = await conn.execute(
            "DELETE FROM rag_solve_jobs WHERE quiz_attempt_id = $1",
            attempt_id,
        )
        deleted = 0
        if isinstance(result, str) and result.upper().startswith("DELETE "):
            try:
                deleted = int(result.split()[-1])
            except ValueError:
                deleted = 0
        return {"ok": True, "attemptId": attempt_id, "deletedCount": deleted}
    finally:
        await conn.close()


@app.delete("/api/admin/quiz-attempts/{attempt_id}")
async def admin_delete_quiz_attempt(attempt_id: int, request: Request):
    await _require_admin_perm(request, "quiz", "delete")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("DELETE FROM rag_solve_jobs WHERE quiz_attempt_id = $1", attempt_id)
        await conn.execute("DELETE FROM quiz_attempt_answers WHERE attempt_id = $1", attempt_id)
        result = await conn.execute("DELETE FROM quiz_attempts WHERE id = $1", attempt_id)
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="퀴즈 기록을 찾을 수 없습니다.")
        return {"ok": True, "deletedId": attempt_id}
    finally:
        await conn.close()


# ── 문제 목록 ──
@app.get("/api/admin/questions")
async def admin_list_questions(request: Request, limit: int = 50, offset: int = 0, subject: str = ""):
    await _require_admin_perm(request, "questions", "read")
    safe_limit = min(max(int(limit or 20), 1), 500)
    safe_offset = min(max(int(offset or 0), 0), 500_000)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        where = "WHERE subject ILIKE $3" if subject else ""
        params = [safe_limit, safe_offset, f"%{subject}%"] if subject else [safe_limit, safe_offset]
        rows = await conn.fetch(
            f"""SELECT id, subject, question, option1, option2, option3, option4, answer
                FROM questions {where} ORDER BY id LIMIT $1 OFFSET $2""",
            *params
        )
        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) FROM questions {'WHERE subject ILIKE $1' if subject else ''}",
            *([ f"%{subject}%" ] if subject else [])
        )
        return {"ok": True, "total": total_row[0], "questions": [
            {"id": r["id"], "subject": r["subject"], "question": r["question"],
             "option1": r["option1"], "option2": r["option2"],
             "option3": r["option3"], "option4": r["option4"], "answer": r["answer"]}
            for r in rows
        ]}
    finally:
        await conn.close()


# ── DB 테이블 통계 (대시보드용) ──
@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    await _require_admin(request)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await _ensure_chat_schema(conn)
        stats = {}
        tables = ["users", "api_request_logs", "rag_solve_jobs", "quiz_attempts",
                  "quiz_attempt_answers", "questions", "user_api_tokens", "refresh_tokens", "forge_chat_conversations", "forge_chat_conversation_shares"]
        for t in tables:
            row = await conn.fetchrow(f"SELECT COUNT(*) FROM {t}")
            stats[t] = row[0]
        # 최근 24h 로그
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM api_request_logs WHERE created_at > NOW() - INTERVAL '24 hours'"
        )
        stats["logs_24h"] = row[0]
        # RAG 완료율
        row = await conn.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE status='completed') AS done, COUNT(*) AS total FROM rag_solve_jobs"
        )
        stats["rag_completed"] = row["done"]
        stats["rag_total"] = row["total"]
        return {"ok": True, "stats": stats}
    finally:
        await conn.close()


