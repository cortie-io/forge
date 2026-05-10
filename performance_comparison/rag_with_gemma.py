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
    extract_json_object,
    format_compliance_score,
    load_questions,
    parse_choice,
)


def build_solve_item(row: QuestionRow) -> Dict[str, Any]:
    return {
        "q": row.question,
        "opts": ", ".join(f"{idx + 1}) {opt}" for idx, opt in enumerate(row.options)),
        "ans": row.answer,
        "wrong": "-",
        "search_query": row.question,
        "user_message": "문제 전체를 기준으로 근거를 검색한다.",
    }


def call_rag_solve(row: QuestionRow, api_base: str, timeout: int) -> List[Dict[str, Any]]:
    url = api_base.rstrip("/") + "/api/v1/rag/solve"
    payload = {"items": [build_solve_item(row)], "rebuild_db": False}
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    result = (data.get("results") or [{}])[0]
    evidence = result.get("evidence") or []
    docs: List[Dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        docs.append({"id": item.get("id"), "text": text})
    return docs


def build_prompt(row: QuestionRow, evidence_text: str) -> str:
    return (
        "너는 네트워크관리사 2급 튜터다. 아래 문제와 근거를 사용해 반드시 JSON으로만 답하라.\n"
        "JSON 스키마: {\"answer\":\"1~4\",\"reason\":\"...\",\"elimination\":{\"1\":\"...\",\"2\":\"...\",\"3\":\"...\",\"4\":\"...\"},\"summary\":\"...\"}\n"
        "규칙: answer는 숫자만, elimination은 4개 모두 채워라. 근거 범위 밖 단정은 피하라.\n\n"
        f"{build_question_blob(row)}\n\n[근거]\n{evidence_text}"
    )


def call_ollama(prompt: str, model: str, host: str, timeout: int) -> str:
    url = host.rstrip("/") + "/api/generate"
    resp = requests.post(
        url,
        json={"model": model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return str(resp.json().get("response", "") or "")


def run_rag_with_gemma(
    input_csv: str,
    output_csv: str,
    model: str,
    ollama_host: str,
    api_base: str,
    limit: int,
    timeout: int,
) -> None:
    rows = load_questions(input_csv, limit=limit)
    total = len(rows)
    out_rows: List[Dict[str, Any]] = []
    raw_json_path = output_csv.replace(".csv", "_raw.jsonl")

    print(f"[B: Naive-RAG] 시작 — {total}문제 | 모델: {model} | Ollama: {ollama_host}", flush=True)

    with open(raw_json_path, "w", encoding="utf-8") as jf:
        for idx, row in enumerate(rows, start=1):
            started = time.time()
            predicted = ""
            explanation = ""
            evidence_text = ""
            evidence_json = "[]"
            raw_response = ""
            error = ""

            try:
                evidence_docs = call_rag_solve(row, api_base=api_base, timeout=timeout)
                evidence_text = "\n\n".join(str(doc.get("text", "")) for doc in evidence_docs[:4])
                evidence_json = json.dumps(evidence_docs[:8], ensure_ascii=False)
                raw_response = call_ollama(build_prompt(row, evidence_text), model=model, host=ollama_host, timeout=timeout)
                parsed = extract_json_object(raw_response)
                predicted = parse_choice(str(parsed.get("answer", "")))
                elimination = parsed.get("elimination") if isinstance(parsed.get("elimination"), dict) else {}
                explanation = canonical_explanation(
                    answer=predicted or "-",
                    reason=str(parsed.get("reason", "")).strip() or "근거를 충분히 생성하지 못했습니다.",
                    elimination={str(k): str(v) for k, v in elimination.items()},
                    summary=str(parsed.get("summary", "")).strip() or "핵심 개념을 다시 확인하세요.",
                )
            except Exception as exc:
                error = str(exc)
                explanation = canonical_explanation(
                    answer="-",
                    reason="RAG+모델 호출 실패",
                    elimination={"1": "", "2": "", "3": "", "4": ""},
                    summary="재시도 필요",
                )

            elapsed = time.time() - started
            row_data = {
                "mode": "naive_rag",
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
                "retrieved_k": len(json.loads(evidence_json)),
                "format_score": format_compliance_score(explanation),
                "evidence_coverage": round(evidence_coverage_score(explanation, evidence_text), 4),
                "latency_sec": round(elapsed, 3),
                "error": error,
            }
            out_rows.append(row_data)

            # raw JSON 저장
            jf.write(json.dumps({"index": idx, "raw_response": raw_response, "evidence_docs": json.loads(evidence_json), "parsed": row_data}, ensure_ascii=False) + "\n")
            jf.flush()

            # 실시간 진행률
            pct = idx / total * 100
            correct_so_far = sum(r["is_correct"] for r in out_rows)
            mark = "✓" if row_data["is_correct"] else "✗"
            q_short = row.question[:30].replace("\n", " ")
            print(f"[B | {idx:3d}/{total} | {pct:5.1f}%] {mark} AI:{predicted or '-'} 정답:{row.answer} ({elapsed:.1f}s) | 누적정답률:{correct_so_far/idx*100:.1f}% | {q_short}…", flush=True)

    pd.DataFrame(out_rows).to_csv(output_csv, index=False, encoding="utf-8-sig")
    correct_total = sum(r["is_correct"] for r in out_rows)
    print(f"\n[B: Naive-RAG 완료] rows={total} | 정답률={correct_total/total*100:.1f}% | CSV={output_csv} | JSONL={raw_json_path}", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="sample_120_questions.csv")
    p.add_argument("--output", default="results/rag_with_gemma_results.csv")
    p.add_argument("--model", default="gemma3:latest")
    p.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    p.add_argument("--api-base", default="http://127.0.0.1:8001")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--timeout", type=int, default=180)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_rag_with_gemma(
        input_csv=args.input,
        output_csv=args.output,
        model=args.model,
        ollama_host=args.ollama_host,
        api_base=args.api_base,
        limit=args.limit,
        timeout=args.timeout,
    )
