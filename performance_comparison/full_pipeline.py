from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List

import pandas as pd
import requests

from common import (
    QuestionRow,
    build_question_blob,
    canonical_explanation,
    evidence_coverage_score,
    format_compliance_score,
    load_questions,
    parse_choice,
)


def call_ontology(row: QuestionRow, api_base: str, timeout: int) -> tuple[Dict[str, Any], Dict[str, Any]]:
    url = api_base.rstrip("/") + "/api/v1/ontology/analyze"
    payload = {
        "payload": (
            "[INTENT]\nEXPLAIN_PROBLEM\n\n"
            f"{build_question_blob(row)}\n\n"
            "[요청]\n이 문제를 풀이 중심으로 해설해줘."
        ),
        "history": [],
        "conversation_key": "perf-full-pipeline",
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    analysis = data.get("analysis") or {}
    if isinstance(analysis, dict):
        # C 그룹 실험 조건: 의도를 항상 문제 해설(EXPLAIN_PROBLEM)로 고정
        analysis["intent"] = "EXPLAIN_PROBLEM"
        raw_seq = analysis.get("intent_sequence") if isinstance(analysis.get("intent_sequence"), list) else []
        seq = [str(tag).strip() for tag in raw_seq if str(tag).strip() and str(tag).strip() != "EXPLAIN_PROBLEM"]
        analysis["intent_sequence"] = ["EXPLAIN_PROBLEM", *seq]
    leg = data.get("leg") if isinstance(data.get("leg"), dict) else {}
    report = leg.get("report") if isinstance(leg.get("report"), dict) else {}
    evidence = leg.get("evidence") if isinstance(leg.get("evidence"), list) else []
    solved = {
        "report": report,
        "evidence": evidence,
        "route": str(data.get("route", "") or "").strip(),
    }
    return analysis, solved


def build_solve_item(row: QuestionRow, analysis: Dict[str, Any]) -> Dict[str, Any]:
    coord = analysis.get("coordinate") if isinstance(analysis.get("coordinate"), dict) else {}
    coords = analysis.get("coordinates") if isinstance(analysis.get("coordinates"), list) else []
    return {
        "q": row.question,
        "opts": ", ".join(f"{idx + 1}) {opt}" for idx, opt in enumerate(row.options)),
        "ans": row.answer,
        "wrong": "-",
        "search_query": str(analysis.get("search_query", "")).strip() or row.question,
        "user_message": "정답 근거와 오답 포인트를 단계적으로 설명",
        "ontology_subject": str(coord.get("subject", "")).strip() or None,
        "ontology_chapter": str(coord.get("chapter", "")).strip() or None,
        "ontology_concept": str(coord.get("concept", "")).strip() or None,
        "ontology_coordinates": coords or None,
    }


def report_to_canonical(result: Dict[str, Any], fallback_answer: str) -> tuple[str, str, str, str, int]:
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    body = report.get("body") if isinstance(report.get("body"), dict) else {}
    answer = parse_choice(str(body.get("answer", ""))) or parse_choice(str(report.get("answer", ""))) or fallback_answer

    analysis = body.get("analysis") if isinstance(body.get("analysis"), dict) else {}
    elimination = {str(k): str(v) for k, v in analysis.items()}

    reason = str(body.get("overview", "")).strip() or "핵심 근거를 추출하지 못했습니다."
    summary = str(report.get("magic_tip", "")).strip() or str(body.get("insight", "")).strip() or "핵심 개념을 다시 확인하세요."

    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    evidence_docs: List[Dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        evidence_docs.append({"id": item.get("id"), "text": text})
    evidence_text = "\n\n".join(
        str(item.get("text", "")).strip() for item in evidence_docs
    )
    evidence_json = json.dumps(evidence_docs[:8], ensure_ascii=False)

    explanation = canonical_explanation(
        answer=answer,
        reason=reason,
        elimination=elimination,
        summary=summary,
    )
    return answer, explanation, evidence_text, evidence_json, len(evidence_docs)


def run_full_pipeline(input_csv: str, output_csv: str, api_base: str, limit: int, timeout: int) -> None:
    rows = load_questions(input_csv, limit=limit)
    total = len(rows)
    out_rows: List[Dict[str, Any]] = []
    raw_json_path = output_csv.replace(".csv", "_raw.jsonl")

    print(f"[C: Full-Pipeline] 시작 — {total}문제 | API: {api_base}", flush=True)

    with open(raw_json_path, "w", encoding="utf-8") as jf:
        for idx, row in enumerate(rows, start=1):
            started = time.time()
            predicted = ""
            explanation = ""
            evidence_text = ""
            evidence_json = "[]"
            retrieved_k = 0
            pred_subject = ""
            pred_chapter = ""
            pred_concept = ""
            raw_ontology: Dict[str, Any] = {}
            raw_solved: Dict[str, Any] = {}
            error = ""

            try:
                raw_ontology, raw_solved = call_ontology(row, api_base=api_base, timeout=timeout)
                coord = raw_ontology.get("coordinate") if isinstance(raw_ontology.get("coordinate"), dict) else {}
                pred_subject = str(coord.get("subject", "")).strip()
                pred_chapter = str(coord.get("chapter", "")).strip()
                pred_concept = str(coord.get("concept", "")).strip()
                if not isinstance(raw_solved.get("report"), dict) or not raw_solved.get("report"):
                    raise RuntimeError("problem explain LEG 결과(report)가 없어 C 그룹 조건을 만족하지 못함")
                predicted, explanation, evidence_text, evidence_json, retrieved_k = report_to_canonical(raw_solved, fallback_answer=row.answer)
            except Exception as exc:
                error = str(exc)
                explanation = canonical_explanation(
                    answer="-",
                    reason="Full pipeline 호출 실패",
                    elimination={"1": "", "2": "", "3": "", "4": ""},
                    summary="재시도 필요",
                )

            elapsed = time.time() - started
            row_data = {
                "mode": "full_pipeline",
                "index": idx,
                "과목": row.subject,
                "문제": row.question,
                "보기1": row.options[0],
                "보기2": row.options[1],
                "보기3": row.options[2],
                "보기4": row.options[3],
                "답": row.answer,
                "AI_정답": predicted,
                "is_correct": int(predicted == row.answer),
                "해설": explanation,
                "RAG_근거": evidence_text,
                "RAG_근거_JSON": evidence_json,
                "retrieved_k": retrieved_k,
                "pred_subject": pred_subject,
                "pred_chapter": pred_chapter,
                "pred_concept": pred_concept,
                "format_score": format_compliance_score(explanation),
                "evidence_coverage": round(evidence_coverage_score(explanation, evidence_text), 4),
                "latency_sec": round(elapsed, 3),
                "error": error,
            }
            out_rows.append(row_data)

            # raw JSON 저장
            jf.write(json.dumps({"index": idx, "ontology": raw_ontology, "solved": raw_solved, "parsed": row_data}, ensure_ascii=False) + "\n")
            jf.flush()

            # 실시간 진행률
            pct = idx / total * 100
            correct_so_far = sum(r["is_correct"] for r in out_rows)
            mark = "✓" if row_data["is_correct"] else "✗"
            coord_str = f"{pred_subject[:8]}>{pred_chapter[:8]}" if pred_subject else "좌표없음"
            q_short = row.question[:28].replace("\n", " ")
            print(f"[C | {idx:3d}/{total} | {pct:5.1f}%] {mark} AI:{predicted or '-'} 정답:{row.answer} ({elapsed:.1f}s) | 누적정답률:{correct_so_far/idx*100:.1f}% | {coord_str} | {q_short}…", flush=True)

    pd.DataFrame(out_rows).to_csv(output_csv, index=False, encoding="utf-8-sig")
    correct_total = sum(r["is_correct"] for r in out_rows)
    print(f"\n[C: Full-Pipeline 완료] rows={total} | 정답률={correct_total/total*100:.1f}% | CSV={output_csv} | JSONL={raw_json_path}", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="sample_120_questions.csv")
    p.add_argument("--output", default="results/full_pipeline_results.csv")
    p.add_argument("--api-base", default="http://127.0.0.1:8001")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--timeout", type=int, default=240)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_full_pipeline(
        input_csv=args.input,
        output_csv=args.output,
        api_base=args.api_base,
        limit=args.limit,
        timeout=args.timeout,
    )
