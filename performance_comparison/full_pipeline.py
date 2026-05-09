import pandas as pd

def run_full_pipeline(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    results = []
    for idx, row in df.iterrows():
        # TODO: 기존 전체 파이프라인(중간 가공 포함) 실행하여 해설 생성
        explanation = "Full Pipeline 해설 결과 (여기에 실제 해설 삽입)"
        results.append({**row, 'FullPipeline_해설': explanation})
    pd.DataFrame(results).to_csv(output_csv, index=False)

if __name__ == "__main__":
    run_full_pipeline(
        "sample_120_questions.csv",
        "results/full_pipeline_results.csv"
    )
