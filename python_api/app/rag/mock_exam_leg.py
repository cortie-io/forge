from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

from langchain_ollama import ChatOllama

from .concept_explain_leg import build_concept_explain_leg_prompt
from .models import EvidenceItem
from .problem_explain_leg import (
    extract_problem_explain_leg_json,
    has_nonempty_problem_explain_leg_refined,
    is_problem_explain_leg_audit_consistent,
    is_problem_explain_leg_body_valid,
    normalize_problem_explain_leg_report,
    repair_problem_explain_leg_audit,
)
from .mcq_payload import format_leg_report_for_chat
from .engine import solve_items
from ..settings import settings


def build_mock_exam_context_for_leg(context: Dict[str, Any], payload_raw: str, *, wrong_questions_fn, find_question_fn, extract_question_numbers_fn) -> str:
    subject_stats = context.get("subject_stats") or {}
    wrong_items = wrong_questions_fn(context)
    numbers = extract_question_numbers_fn(payload_raw)
    focused = [find_question_fn(context, num) for num in numbers[:3]]
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


def build_mock_exam_leg_reply(
    context: Dict[str, Any],
    payload_raw: str,
    history: List[Dict[str, str]],
    *,
    wrong_questions_fn,
    find_question_fn,
    extract_question_numbers_fn,
    top_concepts_fn,
    build_concept_reply_fn,
    build_general_reply_fn,
    extract_requested_question_count_fn,
    payload_wants_question_search_fn,
) -> Dict[str, Any]:
    history_lines: List[str] = []
    for message in history[-6:]:
        role = str(message.get("role", "user") or "user").strip()
        content = str(message.get("content", "") or "").strip()
        if content:
            history_lines.append(f"[{role}] {content[:700]}")
    history_text = "\n".join(history_lines) if history_lines else "-"
    context_text = build_mock_exam_context_for_leg(
        context,
        payload_raw,
        wrong_questions_fn=wrong_questions_fn,
        find_question_fn=find_question_fn,
        extract_question_numbers_fn=extract_question_numbers_fn,
    )

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
    leg_reply = str(llm.invoke(prompt, think=False).content or "").strip()
    if not leg_reply:
        leg_reply = ""

    out: Dict[str, Any] = {
        "ok": True,
        "assistant_message": leg_reply,
        "route": "mock-exam>leg",
        "mock_summary": {
            "wrong_count": len(wrong_questions_fn(context)),
            "top_concepts": top_concepts_fn(context, limit=5),
        },
    }

    sequence = []
    if False:
        sequence = []

    return out
