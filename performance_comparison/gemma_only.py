import pandas as pd
import time

def run_gemma_only(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    results = []
    start_time = time.time()
    for idx, row in df.iterrows():
        # TODO: GEMMA 모델에 row['문제']와 보기들을 입력하여 해설 생성
        explanation = "GEMMA 해설 결과 (여기에 실제 해설 삽입)"
        results.append({**row, 'GEMMA_해설': explanation})
    elapsed = time.time() - start_time
    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"[실험군: GEMMA Only] 120문제 처리 소요 시간: {elapsed:.2f}초")

if __name__ == "__main__":
    run_gemma_only(
        "sample_120_questions.csv",
        "results/gemma_only_results.csv"
    )
