from __future__ import annotations

import json
import re
from typing import Any, Dict

from langchain_ollama import ChatOllama


PROBLEM_EXPLAIN_LEG_TEMPLATE = """
당신은 네트워크 관리사 2급 분야에서 가장 쉽고 친절하게 가르치는 '1타 강사'입니다.  
주어진 [지식 소스]의 내용을 바탕으로 학습자에게 전문적이면서도 다정한 해설을 제공합니다.

---

[필수 준수 규칙]

0. [가장 중요: 근거 기반]  
- 모든 핵심 설명(개념, 정답 판단, 비교 분석)은 반드시 [지식 소스]에 근거하여 작성하세요.  
- 근거 없이 추론한 내용을 단정적으로 말하지 마세요.  
- [지식 소스]에서 근거를 찾지 못한 경우에만 문장 앞에 "[!]"를 붙이고 배경지식을 활용하세요.  
- 설명을 먼저 제시하고, 필요한 경우에만 자연스럽게 보충 설명을 덧붙이세요.

---

1. 페르소나 및 표현 방식  
- 친절한 구어체(~해요, ~예요)를 사용하세요.  
- "교재", "원문", "PDF", "근거", "데이터"라는 단어는 절대 사용하지 마세요.  
- 대신 아래 표현을 활용하세요:  
  → "분석 결과에 따르면"  
  → "핵심 이론상"  
  → "네트워크 원리상"  
- 사람이 직접 가르치는 것처럼 자연스럽게 설명하세요.

---

2. 핵심 설명 구조 (매우 중요)  
- overview 시작 시, 핵심 개념을 한 문장으로 먼저 요약하세요.  
- 이후 개념 → 적용 → 결론 흐름으로 설명하세요.  
- 계산이나 판단이 필요한 경우, 반드시 단계적으로 사고 과정을 보여주세요.  
- 단순 결과가 아니라 “왜 그렇게 되는지”를 중심으로 설명하세요.

---

3. 설명 깊이 강화 규칙  
- 핵심 개념 설명 후, 유사한 간단한 예시를 하나 더 들어 설명하세요.  
- 학습자가 자주 헷갈리는 포인트를 명확하게 짚어주세요.  
- “여기서 많이 틀려요”, “이 부분이 함정이에요” 같은 표현을 적극 활용하세요.  
- 중요한 부분은 천천히 풀어서 설명하고, 단순 정보는 간결하게 설명하세요.

---

4. 상황별 맞춤 해설 로직  

[정답/오답 정보가 있는 경우]  
- 정답이 왜 맞는지 명확히 설명하세요.  
- 사용자가 선택한 오답이 왜 틀렸는지 비교 분석하세요.  

[정답/오답 정보가 없는 경우("-")]  
- [지식 소스]를 기반으로 문제를 직접 해결하세요.  

[body > analysis]  
- 정답 보기는 더 자세하고 명확하게 설명하세요.  
- 오답 보기는 핵심적으로 틀린 이유만 간결하게 설명하세요.  

[body > correction]  
- 사용자의 오답 선택 이유를 추정하고,  
  왜 그런 착각이 생기는지까지 설명하세요.  
- 정답/오답 정보가 없는 경우에는 문제의 핵심 함정이나 시험 포인트를 설명하세요.  

[body > answer]  
- 제공된 정답이 있으면 해당 정답 번호를 사용하세요.  
- 정답이 "-"인 경우, 최종 정답 번호와 보기 내용을 명확히 작성하세요.

---

5. 에비던스 활용 (자연스럽게 숨기기)  
- audit > refined_evidence의 핵심 내용을 해설(overview 또는 correction)에 자연스럽게 녹이세요.  
- 절대로 "근거", "출처", "자료"라는 표현을 직접적으로 사용하지 마세요.  
- 사용자는 눈치채지 못하지만, 설명은 항상 이 내용을 기반으로 구성되어야 합니다.

---

6. 에비던스 정제 규칙 (중요)  
- audit > refined_evidence는 내용을 요약하거나 축약하지 마세요.  
- 원문의 정보량과 의미를 그대로 유지하세요.  
- 문장 구조와 표현만 자연스럽고 읽기 쉽게 다듬으세요.  
- 불필요한 기호, 줄바꿈, 깨진 표현만 정리하세요.  
- 절대로 새로운 정보를 추가하거나 기존 내용을 제거하지 마세요.  
- 가능하면 원문의 문장 순서를 유지하세요.  
- 여러 문장을 하나로 합치지 마세요.

---

7. insight 작성 규칙  
- 단순 비유가 아니라, 문제 풀이에 바로 연결되는 직관으로 설명하세요.  
- 학습자가 “아 그래서 이렇게 푸는구나”라고 느끼게 작성하세요.

---

8. magic_tip 작성 규칙  
- 시험장에서 바로 사용할 수 있는 짧고 강력한 암기법으로 작성하세요.  
- 한 줄 또는 두 줄 이내로 간결하게 작성하세요.

---

9. 사용자 추가 요청 · 대화 맥락 반영 (매우 중요)
- [사용자 요청]에는 [이전 대화 맥락]이 함께 올 수 있습니다. 앞서 학습자·튜터가 나눈 내용을 읽고, 해설이 그 대화와 이어지는 것처럼 자연스럽게 작성하세요(이전에 짚은 오해·용어·문제를 참조).
- 학습자 추가 요청(예: 초보자 눈높이, 단계별 풀이, 비교 중심 설명, 특정 포맷 요구)은 가능한 범위에서 우선 반영하세요.
- 단, [지식 소스]와 충돌하는 요청은 그대로 따르지 말고, 충돌 이유를 부드럽게 설명한 뒤 근거 기반으로 해설하세요.
- 맥락·추가 요청이 비어 있거나 "-"만 있는 경우에는 기존 기본 해설 정책을 따르세요.

---

지식 소스: {context}  
문제 데이터: {question}
사용자 요청: {user_message}

---

JSON 응답:
{{
  "header": {{ "ans": "정답 번호", "keyword": "핵심 키워드", "level": "난이도" }},
  "body": {{
    "overview": "핵심 개념 한 줄 요약 + 단계적 설명 + 추가 예시 포함",
    "analysis": {{
      "1": "보기1 분석",
      "2": "보기2 분석",
      "3": "보기3 분석",
      "4": "보기4 분석"
    }},
    "correction": "오답 원인 분석 또는 핵심 함정 설명",
    "insight": "직관적 이해 설명",
    "answer": "최종 정답"
  }},
  "audit": {{
    "source": "RAG 백터 DB",
    "user_request_trace": {{
      "detected": true,
      "quote": "사용자 메시지 원문 일부",
      "applied_instruction": "해설에 반영한 요청 요약"
    }},
    "refined_evidence": [
      {{ "id": 번호, "text": "원문 의미 유지 + 문장만 정리된 내용" }}
    ]
  }},
  "magic_tip": "시험장에서 쓰는 암기 팁"
}}
"""

_EVIDENCE_ENFORCE_TEMPLATE = """

[추가 강제 규칙: audit.refined_evidence]
- refined_evidence에는 반드시 {min_evidence}개 이상, 최대 {max_evidence}개의 항목을 작성하세요.
- 서로 다른 id만 사용하세요(중복 id 금지).
- id는 반드시 1 이상 {doc_count} 이하의 정수만 사용하세요.
- 각 text는 비어있지 않게 작성하고, 문제와 관련된 내용만 포함하세요.
"""


def extract_problem_explain_leg_json(text: str) -> Dict[str, Any]:
    candidates: list[tuple[dict, int]] = []
    fenced = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    for fb in fenced:
        try:
            obj = json.loads(fb.strip())
            candidates.append((obj, 8))
        except Exception:
            continue
    for match in re.finditer(r"\{[\s\S]*?\}", text):
        try:
            obj = json.loads(match.group(0))
            candidates.append((obj, 5))
        except Exception:
            continue
    for i, char in enumerate(text):
        if char == "{":
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[i:])
                candidates.append((obj, 3))
            except Exception:
                continue

    def score_obj(obj: dict) -> int:
        if not isinstance(obj, dict):
            return -1
        score = 0
        for key in ["header", "body", "audit", "magic_tip"]:
            score += 3 if key in obj else 0
        if "general" not in ["header", "body", "audit", "magic_tip"]:
            score += min(6, len(obj.keys())) if obj.keys() else 0
        return score

    if candidates:
        scored = [(obj, score_obj(obj) + s) for obj, s in candidates]
        best = max(scored, key=lambda x: x[1])
        return best[0]
    return {"error": "JSON_EXTRACT_FAILED"}


def normalize_problem_explain_leg_report(report: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(report, dict):
        return report
    if "body" in report and isinstance(report["body"], dict):
        return report
    flat_keys = {"overview", "analysis", "correction", "insight", "answer"}
    if any(k in report for k in flat_keys):
        body = {}
        for key in flat_keys:
            if key in report:
                body[key] = report.pop(key)
        report["body"] = body
    return report


def is_problem_explain_leg_audit_consistent(report: Dict[str, Any]) -> bool:
    if not isinstance(report, dict) or "audit" not in report:
        return False
    refined_evidence = report.get("audit", {}).get("refined_evidence", [])
    if not isinstance(refined_evidence, list) or len(refined_evidence) == 0:
        return False
    for item in refined_evidence:
        if not isinstance(item, dict):
            return False
        if not item.get("id") or not str(item.get("text", "")).strip():
            return False
    return True


def has_nonempty_problem_explain_leg_refined(report: Dict[str, Any]) -> bool:
    if not isinstance(report, dict) or "audit" not in report:
        return False
    refined_evidence = report.get("audit", {}).get("refined_evidence", [])
    if not refined_evidence:
        return False
    unique_ids = set()
    total_len = 0
    longest = 0
    for item in refined_evidence:
        if isinstance(item, dict):
            try:
                eid = int(item.get("id", 0))
            except (ValueError, TypeError):
                continue
            if eid > 0:
                unique_ids.add(eid)
            text = str(item.get("text", "")).strip()
            tlen = len(text)
            total_len += tlen
            if tlen > longest:
                longest = tlen
    if len(unique_ids) == 0:
        return False
    if longest < 40:
        return False
    if total_len < 80:
        return False
    return True


def is_problem_explain_leg_body_valid(report: Dict[str, Any]) -> bool:
    if not isinstance(report, dict):
        return False
    body = report.get("body", {})
    if not isinstance(body, dict) or not body:
        return False
    overview = str(body.get("overview", "")).strip()
    analysis = body.get("analysis", {})
    if len(overview) < 30:
        return False
    if not isinstance(analysis, dict) or len(analysis) == 0:
        return False
    return True


def build_problem_explain_leg_prompt(
    context: str,
    payload: str,
    doc_count: int,
    user_message: str = "",
) -> str:
    min_evidence = 2 if doc_count >= 3 else 1
    max_evidence = min(4, max(1, doc_count))
    return (
        PROBLEM_EXPLAIN_LEG_TEMPLATE.format(
            context=context,
            question=payload,
            user_message=(user_message or "-"),
        )
        + _EVIDENCE_ENFORCE_TEMPLATE.format(
            min_evidence=min_evidence,
            max_evidence=max_evidence,
            doc_count=doc_count,
        )
    )


def repair_problem_explain_leg_audit(report: dict, docs: list, llm: ChatOllama) -> dict:
    if not isinstance(report, dict) or "audit" not in report:
        return report
    audit = report.get("audit", {})
    raw_refined = audit.get("refined_evidence", [])
    valid_refined = []
    for item in raw_refined:
        if not isinstance(item, dict):
            continue
        try:
            eid = int(item.get("id", 0))
        except (ValueError, TypeError):
            continue
        if 1 <= eid <= len(docs):
            valid_refined.append(eid)
    if not valid_refined:
        print("[Forge-Log] refined_evidence 비어있음. audit 초기화.")
        audit["evidence_ids"] = []
        audit["refined_evidence"] = []
        return report

    refined_map = {}
    for item in raw_refined:
        if isinstance(item, dict) and item.get("id"):
            try:
                eid = int(item["id"])
                text = str(item.get("text", "")).strip()
                if len(text) >= 50:
                    refined_map[eid] = text
            except (ValueError, TypeError):
                pass

    final_refined = []
    seen_ids = set()
    for eid in valid_refined:
        if eid in seen_ids:
            for existing in final_refined:
                if existing["id"] == eid:
                    additional = refined_map.get(eid) or docs[eid - 1].page_content.strip()
                    existing["text"] = existing["text"] + " " + additional
                    break
            continue
        seen_ids.add(eid)
        text = refined_map.get(eid) or docs[eid - 1].page_content.strip()
        final_refined.append({"id": eid, "text": text})

    min_needed = 2 if len(docs) >= 3 else 1
    if len(seen_ids) < min_needed:
        for idx, doc in enumerate(docs, start=1):
            if idx in seen_ids:
                continue
            fallback_text = doc.page_content.strip()
            if len(fallback_text) < 30:
                continue
            final_refined.append({"id": idx, "text": fallback_text})
            seen_ids.add(idx)
            if len(seen_ids) >= min_needed:
                break

    audit["evidence_ids"] = list(seen_ids)
    audit["refined_evidence"] = final_refined
    return report
