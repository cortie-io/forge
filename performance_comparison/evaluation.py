import openai
import pandas as pd

# LLM judge 프롬프트 예시
FAITHFULNESS_PROMPT = """
너는 네트워크 관리사 2급 시험의 감독관이야. 아래 [근거 문서]와 [AI의 해설]을 비교해서 Faithfulness 점수를 매겨줘. 해설의 문장 중 근거 문서에 없는 내용을 말하면 감점이야. 점수는 0에서 1 사이로 산출해.
[근거 문서]: {evidence}
[AI의 해설]: {explanation}
점수만 숫자로 답해줘.
"""

RELEVANCE_PROMPT = """
너는 네트워크 관리사 2급 시험의 감독관이야. 아래 [AI의 해설]을 보고, 정답 근거, 오답 소거, 쉬운 비유가 얼마나 잘 포함되어 있는지 1~5점으로 평가해줘. 점수만 숫자로 답해줘.
[AI의 해설]: {explanation}
"""

def ask_llm(prompt, model="gpt-4o"):
    # 실제로는 openai.ChatCompletion.create 등으로 구현
    # 예시: return float(openai.ChatCompletion.create(...))
    # 여기선 더미값 반환
    import random
    return round(random.uniform(0.5, 1.0), 2)

def evaluate_row(row, group):
    # 근거 충실도
    faithfulness = ask_llm(FAITHFULNESS_PROMPT.format(evidence=row.get('RAG_근거', ''), explanation=row.get('해설', '')))
    # 근거 정밀도: 실제 구현 필요 (여기선 더미)
    context_precision = row.get('ContextPrecision', 0.0)
    # 정답 정확도
    answer_correct = int(str(row.get('답', '')).strip() == str(row.get('AI_정답', '')).strip())
    # 가독성/논리성
    relevance = ask_llm(RELEVANCE_PROMPT.format(explanation=row.get('해설', '')))
    return faithfulness, context_precision, answer_correct, relevance


import time
def evaluate_file(input_csv, output_csv, group):
    df = pd.read_csv(input_csv)
    results = []
    start_time = time.time()
    for _, row in df.iterrows():
        faith, ctx_prec, correct, rel = evaluate_row(row, group)
        results.append({**row,
            '근거충실도': faith,
            '근거정밀도': ctx_prec,
            '정답정확도': correct,
            '가독성': rel
        })
    elapsed = time.time() - start_time
    pd.DataFrame(results).to_csv(output_csv, index=False)
    print(f"[평가] {group} 120문제 평가 소요 시간: {elapsed:.2f}초")

if __name__ == "__main__":
    # 예시 실행
    evaluate_file("results/full_pipeline_results.csv", "results/full_pipeline_evaluated.csv", group="C")
