#!/usr/bin/env python3
"""
Precompute RAG 검색어(핵심 키워드) 추출 및 저장 스크립트
- 모든 questions 테이블의 문제에 대해 rewrite LLM을 호출해 검색어를 추출하고, DB에 저장
- DB에 search_query, query_terms 컬럼이 없다면 자동 생성
"""
import os
import psycopg2
from psycopg2.extras import execute_batch
import json
import requests

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://sikdorak_app:sikdorak_password@127.0.0.1:5432/sikdorak"
)

# 서비스 settings와 동일하게 환경변수 사용
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://100.79.44.109:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma4-e4b:latest")
OLLAMA_REWRITE_NUM_PREDICT = int(os.environ.get("OLLAMA_REWRITE_NUM_PREDICT", "128"))
OLLAMA_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))


# 실제 서비스와 동일한 프롬프트
REWRITE_TEMPLATE = """
네트워크 관리사 2급 전문가로서, 교재 검색을 위한 최적의 쿼리를 생성하세요.
반드시 문제의 핵심 용어(개념어, 기술 용어, 고유명사 등)를 포함해야 합니다.
JSON 응답: {{"query": "검색어 조합"}}
[문제]: {payload}
"""


# 실제 서비스와 동일한 JSON 추출 로직
def _extract_json(text):
    import re, json as pyjson
    candidates = []
    # 1. Fenced JSON blocks (```json ... ```)
    fenced = re.findall(r"```(?:json)?\\s*(\{[\s\S]*?\})\\s*```", text)
    if fenced:
        for fb in fenced:
            try:
                obj = pyjson.loads(fb.strip())
                candidates.append((obj, 8))
            except: pass
    # 2. Broader object capture
    for match in re.finditer(r"\{[\s\S]*?\}", text):
        try:
            obj = pyjson.loads(match.group(0))
            candidates.append((obj, 5))
        except: pass
    # 3. Decoder raw_decode from each '{' offset
    for i, char in enumerate(text):
        if char == '{':
            try:
                obj, _ = pyjson.JSONDecoder().raw_decode(text[i:])
                candidates.append((obj, 3))
            except: pass
    # Score candidates by key presence
    def score_obj(obj):
        if not isinstance(obj, dict): return -1
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

# 실제 서비스와 동일한 쿼리 생성 함수
def call_rewrite_llm(question, options, wrong, answer):
    payload = f"문제: {question}\n보기: {options}\n오답: {wrong}\n정답: {answer}"
    prompt = REWRITE_TEMPLATE.format(payload=payload)
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "max_tokens": OLLAMA_REWRITE_NUM_PREDICT,
                "temperature": 0,
                "format": "json"
            },
            headers={"User-Agent": "curl/7.68.0"},
            timeout=10,
            stream=False
        )
        resp.raise_for_status()핵
        print(f"[DEBUG] LLM HTTP status: {resp.status_code}")
        print(f"[DEBUG] LLM raw response: {resp.text}")
        # Ollama/gemma 스트리밍 JSON 라인 파싱
        responses = []
        for line in resp.text.splitlines():
            try:
                obj = json.loads(line)
                if "response" in obj and obj["response"]:
                    responses.append(obj["response"])
            except Exception:
                continue
        text = "".join(responses)
        print(f"[DEBUG] LLM 합쳐진 response: {text}")
        # 서비스와 동일한 JSON 추출
        result = _extract_json(text)
        return result
    except Exception as e:
        print(f"[ERROR] LLM 호출 실패: {e}")
        return {"query": question}

# DB 컬럼 자동 추가
def ensure_columns(cur):
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='questions' AND column_name='search_query') THEN
                ALTER TABLE questions ADD COLUMN search_query TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='questions' AND column_name='query_terms') THEN
                ALTER TABLE questions ADD COLUMN query_terms TEXT;
            END IF;
        END
        $$;
    """)


def main():
    print("[DEBUG] DB 연결 시도...")
    conn = psycopg2.connect(DATABASE_URL)
    print("[DEBUG] DB 연결 성공")
    cur = conn.cursor()
    print("[DEBUG] 컬럼 자동 추가(ensure_columns) 시도...")
    ensure_columns(cur)
    conn.commit()
    print("[DEBUG] questions SELECT 시도...")
    cur.execute("SELECT id, question, option1, option2, option3, option4, answer FROM questions ORDER BY id")
    rows = cur.fetchall()
    print(f"[DEBUG] {len(rows)}개 문제 로드 완료")

    updates = []
    for idx, row in enumerate(rows):
        qid, question, opt1, opt2, opt3, opt4, answer = row
        options = f"{opt1} {opt2} {opt3} {opt4}"
        wrong = ""  # 오답 정보 필요시 수정
        ans = [opt1, opt2, opt3, opt4][answer-1] if 1 <= answer <= 4 else ""
        print(f"[DEBUG] ({idx+1}/{len(rows)}) LLM 호출: id={qid}")
        llm_res = call_rewrite_llm(question, options, wrong, ans)
        search_query = llm_res.get("query", "")
        # 실제 서비스와 동일한 키워드 추출
        def _extract_terms(text):
            import re
            stop = {
                "문제", "보기", "정답", "오답", "다음", "설명", "해설", "분석",
                "선택", "번호", "정답은", "오답은", "대한", "그리고", "또는",
                "the", "and", "for", "with", "from", "this", "that",
            }
            tokens = re.findall(r"[A-Za-z0-9가-힣]+", (text or "").lower())
            terms = set()
            for tok in tokens:
                if len(tok) < 2:
                    continue
                if tok in stop:
                    continue
                if tok.isdigit():
                    continue
                terms.add(tok)
            return terms
        query_terms = ",".join(sorted(_extract_terms(search_query)))
        updates.append((search_query, query_terms, qid))

    print(f"[DEBUG] DB 업데이트 시도 ({len(updates)}건)")
    execute_batch(cur, "UPDATE questions SET search_query=%s, query_terms=%s WHERE id=%s", updates)
    conn.commit()
    print(f"Updated {len(updates)} questions with search_query and query_terms.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
