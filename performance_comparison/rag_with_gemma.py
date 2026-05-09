def run_rag_with_gemma(input_csv, output_csv):
import pandas as pd
import time

def run_rag_with_gemma(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    results = []
    start_time = time.time()
    for idx, row in df.iterrows():
        # Query rewrite 사용하지 않고 문제 전체를 검색어로 사용
        query = row['문제']
        # TODO: RAG에서 query(문제 전체)로 근거 추출
        evidence = f"RAG 근거 자료 (문제 전체로 검색, 실제 근거 삽입)"
        # TODO: GEMMA에 문제+근거 입력하여 해설 생성
        explanation = "GEMMA+RAG 해설 결과 (여기에 실제 해설 삽입)"
        results.append({**row, 'RAG_근거': evidence, 'GEMMA_RAG_해설': explanation})
    elapsed = time.time() - start_time
    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"[실험군: Naive RAG] 120문제 처리 소요 시간: {elapsed:.2f}초")

if __name__ == "__main__":
    run_rag_with_gemma(
        "sample_120_questions.csv",
        "results/rag_with_gemma_results.csv"
    )
