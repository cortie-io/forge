import pandas as pd
import requests
import time

API_URL = "http://localhost:8001/api/v1/rag/solve"  # 실제 서비스 주소로 변경 필요

INPUT_CSV = "sample_120_questions.csv"
OUTPUT_CSV = "results/full_pipeline_results.csv"


def build_payload(row):
    # 문제+보기+정답을 ExamItem 형태로 변환
    # 필수값이 모두 비어있으면 None 반환
    q = str(row["문제"]).strip()
    opts = [str(row["보기1"]).strip(), str(row["보기2"]).strip(), str(row["보기3"]).strip(), str(row["보기4"]).strip()]
    ans = str(row["답"]).strip()
    # wrong(오답) 추출: 정답이 아닌 첫 번째 보기를 오답으로 사용
    wrong = next((o for i, o in enumerate(opts) if str(i+1) != ans), opts[0] if opts else "")
    # 필수값: 문제, 정답, 보기 4개
    if not q or not ans or len(opts) != 4:
        return None
    return {
        "q": q,
        "opts": ",".join(opts),
        "ans": ans,
        "wrong": wrong,
        # 온톨로지 좌표 등 추가 가능
    }

def main():
    df = pd.read_csv(INPUT_CSV, header=0, encoding="utf-8-sig")
    # NaN을 빈 문자열로 변환 (서비스에서 robust하게 막지만, requests.post에서 NaN 허용 안 함)
    df = df.where(pd.notnull(df), '')
    items = [build_payload(row) for _, row in df.iterrows()]
    # None(필수값 없는 row) 제거
    items = [item for item in items if item is not None]
    if not items:
        print("[경고] 유효한 문제가 1개도 없습니다. CSV/필드명/인코딩을 확인하세요.")
    payload = {"items": items, "rebuild_db": False}
    start = time.time()
    resp = requests.post(API_URL, json=payload)
    elapsed = time.time() - start
    if resp.status_code == 200 and resp.json().get("ok"):
        results = resp.json()["results"]
        # 결과를 DataFrame으로 저장
        out_df = pd.DataFrame(results)
        out_df.to_csv(OUTPUT_CSV, index=False)
        print(f"[실험군: Forge] 120문제 처리 소요 시간: {elapsed:.2f}초")
    else:
        print("API 호출 실패:", resp.text)

if __name__ == "__main__":
    main()
