from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

import pandas as pd


SECTION_ORDER = ["정답", "정답 근거", "오답 포인트", "한줄 요약"]


@dataclass
class QuestionRow:
    subject: str
    question: str
    options: List[str]
    answer: str


def load_questions(csv_path: str, limit: int = 0) -> List[QuestionRow]:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df = df.where(pd.notnull(df), "")

    rows: List[QuestionRow] = []
    for _, row in df.iterrows():
        subject = str(row.get("과목", "")).strip()
        question = str(row.get("문제", "")).strip()
        options = [
            str(row.get("보기1", "")).strip(),
            str(row.get("보기2", "")).strip(),
            str(row.get("보기3", "")).strip(),
            str(row.get("보기4", "")).strip(),
        ]
        answer = str(row.get("답", "")).strip()
        if not subject or not question or any(not x for x in options) or not answer:
            continue
        rows.append(QuestionRow(subject=subject, question=question, options=options, answer=answer))
        if limit > 0 and len(rows) >= limit:
            break
    return rows


def build_question_blob(row: QuestionRow) -> str:
    opts = "\n".join(f"{idx + 1}) {opt}" for idx, opt in enumerate(row.options))
    return f"[과목]\n{row.subject}\n\n[문제]\n{row.question}\n\n[보기]\n{opts}"


def canonical_explanation(answer: str, reason: str, elimination: Dict[str, str], summary: str) -> str:
    lines: List[str] = []
    lines.append("[정답]")
    lines.append(f"{str(answer).strip()}번")
    lines.append("")
    lines.append("[정답 근거]")
    lines.append(str(reason).strip())
    lines.append("")
    lines.append("[오답 포인트]")
    for i in range(1, 5):
        key = str(i)
        lines.append(f"{i}) {str(elimination.get(key, "")).strip()}")
    lines.append("")
    lines.append("[한줄 요약]")
    lines.append(str(summary).strip())
    return "\n".join(lines).strip()


def format_compliance_score(text: str) -> float:
    body = str(text or "")
    if not body:
        return 0.0
    score = 0
    for section in SECTION_ORDER:
        if f"[{section}]" in body:
            score += 1
    return score / len(SECTION_ORDER)


def parse_choice(value: str) -> str:
    m = re.search(r"([1-4])", str(value or ""))
    return m.group(1) if m else ""


def extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    for block in fenced:
        try:
            obj = json.loads(block)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue

    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def tokenize_kor_eng(text: str) -> List[str]:
    return re.findall(r"[0-9A-Za-z가-힣]{2,}", str(text or "").lower())


def split_sentences_kor(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    chunks = re.split(r"\n+|(?<=[\.!\?])\s+|(?<=다\.)\s+", raw)
    out = [c.strip() for c in chunks if len(c.strip()) >= 6]
    return out


def token_overlap_ratio(a: str, b: str) -> float:
    ta = set(tokenize_kor_eng(a))
    tb = set(tokenize_kor_eng(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta)


def evidence_coverage_score(explanation: str, evidence: str) -> float:
    exp_tokens = set(tokenize_kor_eng(explanation))
    ev_tokens = set(tokenize_kor_eng(evidence))
    if not exp_tokens or not ev_tokens:
        return 0.0
    overlap = len(exp_tokens & ev_tokens)
    return overlap / max(1, len(exp_tokens))
