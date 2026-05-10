# Measurement Protocol (Explanation-Only)

이 문서는 120문제 실험에서 해설 품질만 평가하기 위한 측정 프로토콜입니다.

## Scope

- 평가 대상: 문제 해설 출력(`해설`)과 최종 선택(`AI_정답`)
- 비평가 대상: UI/대화 UX/멀티턴 효율성/좌표 분류 자체 성능
- 목적: 온톨로지 기반 RAG가 해설 신뢰성과 정답률 개선에 기여하는지 정량 검증

## Core Metrics

1. Faithfulness (근거충실도)

$$
Faithfulness = \frac{N_{supported\_sentences}}{N_{all\_sentences}}
$$

- 해설을 문장 단위로 분할
- 각 문장이 근거 문서 상위 K개 중 하나 이상에 의해 지지되면 supported
- 점수 범위: 0~1

2. Context Precision (근거 정밀도)

- 상위 K 근거 문서의 랭크 가중 관련도 평균
- 현재 구현: 로그 감쇠 가중치 $1/\log_2(rank+1)$ 기반
- 점수 범위: 0~1

3. Answer Correctness (정답정확도)

$$
Correctness = \mathbb{1}[AI\_정답 = 정답]
$$

- 일치 시 1, 불일치 시 0

4. Reasoning Accuracy (추론 정확도)

- 오답 소거 논리 점수
- 전문 용어 정확도

5. LLM-as-a-Judge (필수)

- 1~5 리커트 점수
- 정확성(Accuracy), 완결성(Completeness), 가독성(Clarity) 각각 1~5
- 기본 실행은 `--require-judge=1`이며 API 키 없으면 실패

## Derived Metrics

- Hallucination Rate (환각발생률):

$$
Hallucination = 1 - Faithfulness
$$

- Error Cause:
- 환각/근거미흡
- 잘못된 문서 참조
- 논리 오류
- 설명 불충분

## Group Definitions

- A (LLM-only): 문제만 모델에 입력
- B (Naive RAG): 문제 전체 텍스트로 검색 -> 근거+문제로 생성
- C (Full Pipeline): 온톨로지 분석 -> 좌표/검색쿼리 반영 -> RAG 생성

## Outputs

- 문항별 평가: `results/*_evaluated.csv`
- 요약표: `results/performance_summary.csv`
- 차트:
- `results/grouped_bar_chart.png`
- `results/subject_heatmap.png`
- `results/donut_chart.png`
- 보고서: `results/experiment_report.md`

## Reproducibility

- 모든 생성 모델 호출은 `temperature=0`
- 동일 CSV(`sample_120_questions.csv`) 사용
- 동일 timeout/config 사용
- 결과는 UTF-8-SIG CSV로 저장
- 시간 기록: 생성/판정/평가 지연을 모두 기록(`latency_sec`, `judge_latency_sec`, `eval_latency_sec`)
