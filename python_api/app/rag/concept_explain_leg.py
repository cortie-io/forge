from __future__ import annotations

from typing import Any, Dict


CONCEPT_EXPLAIN_LEG_TEMPLATE = """
당신은 네트워크관리사 2급 학습자를 가르치는 최고의 개념 설명 강사입니다.
주어진 [지식 소스]만을 바탕으로, 이전 대화 맥락과 이번 요청을 함께 고려해 근거 기반 설명을 작성하세요.

[최우선 규칙]
1. 핵심 설명은 반드시 [지식 소스]에 근거해야 합니다.
2. [지식 소스]에 없는 내용은 단정하지 말고, 정말 필요할 때만 매우 조심스럽게 보충하세요.
3. 설명은 친절한 한국어 구어체로 작성하세요.
4. "원문", "근거", "데이터", "문서", "자료"라는 표현은 직접 쓰지 마세요.
5. 이전 대화에서 이미 설명한 오해나 비교 포인트가 있으면 자연스럽게 이어서 설명하세요.

[설명 방식]
- overview: 먼저 핵심 개념을 한 문장으로 요약하고, 바로 전체 구조를 풀어 설명하세요.
- analysis: 학습자가 꼭 잡아야 할 핵심 포인트를 3~4개로 나누어 설명하세요.
- correction: 학습자가 자주 헷갈리는 부분, 틀리기 쉬운 포인트, 잘못 연결하기 쉬운 개념을 설명하세요.
- insight: 실제 문제 풀이 또는 실무/시험 적용 관점에서 직관을 주세요.
- magic_tip: 시험 직전에 떠올릴 수 있는 한 줄 암기 팁을 주세요.

[analysis 작성 규칙]
- 번호별로 서로 다른 핵심 포인트를 써야 합니다.
- 각 포인트는 "개념 -> 왜 중요한지 -> 어떻게 구분하는지" 흐름을 우선하세요.
- 단순 정의 반복보다 비교와 연결을 더 중시하세요.

[audit.refined_evidence 작성 규칙]
- 반드시 2개 이상, 최대 4개의 항목을 작성하세요. 문서가 1개뿐이면 1개만 허용합니다.
- 각 항목의 id는 [지식 소스] 문서 번호와 일치해야 합니다.
- text는 원래 의미와 정보량을 유지하면서 읽기 쉽게만 다듬으세요.
- 새로운 정보를 추가하거나, 중요한 정보를 삭제하지 마세요.

주제: {topic}
이전 대화 맥락: {conversation_context}
사용자 요청: {user_message}
지식 소스: {context}

JSON 응답:
{{
  "header": {{ "kind": "concept", "keyword": "핵심 키워드", "level": "입문|중급|고급" }},
  "body": {{
    "overview": "핵심 개념 한 줄 요약 + 전체 설명",
    "analysis": {{
      "1": "핵심 포인트 1",
      "2": "핵심 포인트 2",
      "3": "핵심 포인트 3"
    }},
    "correction": "헷갈리기 쉬운 포인트",
    "insight": "문제 풀이/실전 적용 직관",
    "answer": ""
  }},
  "audit": {{
    "source": "RAG vector DB",
    "user_request_trace": {{
      "detected": true,
      "quote": "사용자 요청 일부",
      "applied_instruction": "설명에 반영한 요청 요약"
    }},
    "refined_evidence": [
      {{ "id": 1, "text": "의미를 유지하면서 다듬은 설명" }}
    ]
  }},
  "magic_tip": "짧은 암기 팁"
}}
"""


def build_concept_explain_leg_prompt(
    *,
    context: str,
    topic: str,
    conversation_context: str = "-",
    user_message: str = "-",
    doc_count: int = 0,
) -> str:
    min_evidence = 2 if doc_count >= 2 else 1
    max_evidence = min(4, max(1, doc_count or 1))
    return (
        CONCEPT_EXPLAIN_LEG_TEMPLATE.format(
            context=context or "-",
            topic=topic or "-",
            conversation_context=conversation_context or "-",
            user_message=user_message or "-",
        )
        + f"\n\n[추가 강제 규칙]\n- refined_evidence에는 최소 {min_evidence}개, 최대 {max_evidence}개의 항목만 작성하세요.\n"
        + f"- id는 반드시 1 이상 {max(1, doc_count or 1)} 이하의 정수만 사용하세요.\n"
    )


def format_concept_explain_leg_for_chat(report: Dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return "개념 설명 결과를 표시할 수 없습니다."
    lines: list[str] = []
    header = report.get("header") or {}
    if isinstance(header, dict):
        kw = str(header.get("keyword", "") or "").strip()
        lvl = str(header.get("level", "") or "").strip()
        meta = " · ".join(x for x in [kw, lvl] if x)
        if meta:
            lines.append(meta)
    body = report.get("body") or {}
    if isinstance(body, dict):
        overview = str(body.get("overview", "") or "").strip()
        if overview:
            lines.append(overview)
        analysis = body.get("analysis") or {}
        if isinstance(analysis, dict) and analysis:
            lines.append("")
            for key in sorted(analysis.keys(), key=lambda value: str(value)):
                text = str(analysis.get(key, "") or "").strip()
                if text:
                    lines.append(f"[{key}] {text}")
        correction = str(body.get("correction", "") or "").strip()
        if correction:
            lines.append("")
            lines.append(f"헷갈리는 포인트: {correction}")
        insight = str(body.get("insight", "") or "").strip()
        if insight:
            lines.append("")
            lines.append(f"적용: {insight}")
    tip = str(report.get("magic_tip", "") or "").strip()
    if tip:
        lines.append("")
        lines.append(f"시험 팁: {tip}")
    return "\n".join(lines).strip() or "개념 설명이 생성되었지만 본문이 비어 있습니다."