"""
대화 이력 기반 보조: 후속 메시지가 문제 본문만 와도 이전 '해설' 요청과 연결합니다.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

# 이전 사용자 발화에 포함되면 '문제 해설·풀이' 맥락으로 간주
_EXPLAIN_HINT_RE = re.compile(
    r"(해설|문제\s*해설|문제\s*풀이|풀이\s*해|정답|오답|모의고사|"
    r"문제\s*하나|문제만|이\s*문제|아래\s*문제|선지|보기\s*중|"
    r"왜\s*틀|왜\s*맞|알려줘\s*$|설명해)",
    re.I,
)


def history_suggests_problem_explain(history: List[Dict[str, Any]]) -> bool:
    """대화에 사용자의 문제 해설·풀이 요청이 있었는지."""
    if not history:
        return False
    for msg in history:
        if str(msg.get("role", "")).lower() != "user":
            continue
        text = str(msg.get("content", "") or "").strip()
        if not text:
            continue
        if _EXPLAIN_HINT_RE.search(text):
            return True
    return False


def augment_payload_for_ontology_followup(payload: str, history: List[Dict[str, Any]]) -> str:
    """
    온톨로지 LLM이 FOLLOWUP만 내지 않도록, 문제 본문만 온 후속 턴에 맥락 문구를 붙입니다.
    LEG 파싱에는 원문(payload)을 씁니다.
    """
    from .mcq_payload import parse_mcq_from_payload

    p = str(payload or "").strip()
    if not p:
        return p
    if parse_mcq_from_payload(p) and history_suggests_problem_explain(history):
        return (
            "[대화 맥락] 이전 메시지에서 문제 해설 또는 풀이를 요청했습니다. "
            "아래는 이어서 보낸 문제 본문(선지 포함)입니다.\n\n"
            f"{p}"
        )
    return p


def format_history_for_leg_prompt(
    history: List[Dict[str, Any]],
    *,
    max_chars: int | None = None,
    per_message_cap: int = 1800,
) -> str:
    """
    LEG(Problem_Explain) 해설 LLM에 넣기 위한 이전 대화 요약.
    - user/assistant 만 포함, 시간순 유지
    - 한 메시지가 너무 길면 잘라서 전체 상한(max_chars) 안에 맞춤
    """
    if not history:
        return ""
    env_mc = os.getenv("FORGE_LEG_HISTORY_MAX_CHARS", "8000").strip()
    try:
        mc = int(env_mc or "8000")
    except ValueError:
        mc = 8000
    max_chars = max_chars if max_chars is not None else max(500, min(mc, 20000))

    blocks: List[str] = []
    for msg in history:
        role = str(msg.get("role", "") or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        label = "학습자" if role == "user" else "튜터"
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue
        if len(content) > per_message_cap:
            content = content[: per_message_cap - 1] + "…"
        blocks.append(f"[{label}] {content}")
    if not blocks:
        return ""
    while blocks and len("\n".join(blocks)) > max_chars:
        blocks.pop(0)
    return "\n".join(blocks)
