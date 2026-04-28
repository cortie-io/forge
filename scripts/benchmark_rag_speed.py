import time
import requests
from scripts.precompute_question_keywords import call_rewrite_llm

# 10개 샘플 문제 (실제 문제로 교체)
questions = [
    {
        "question": "다음 중 UDP에 대한 설명으로 가장 타당하지 않은 것은?",
        "options": [
            "UDP는 TCP에 비해 신뢰성이 떨어진다.",
            "UDP는 사용자 데이터그램(Datagram)이라고 하는 데이터 유니트를 송신지의 응용 프로세스에서 수신지의 응용 프로세스로 전송한다.",
            "UDP가 제공하는 오류검사는 홀수 패리티와 짝수 패리티가 있다.",
            "UDP가 제공하는 서비스는 비연결형 데이터 전달서비스(Compunctionless Data Delivery Service)이다."
        ],
        "wrong": "",
        "answer": "UDP가 제공하는 오류검사는 홀수 패리티와 짝수 패리티가 있다."
    },
    # ... 9개 더 추가 ...
]

def measure_api_time(api_url, questions):
    times = []
    for q in questions:
        payload = {
            "items": [{
                "q": q["question"],
                "opts": "\n".join(q["options"]),
                "wrong": q["wrong"],
                "ans": q["answer"]
            }]
        }
        start = time.time()
        r = requests.post(api_url, json=payload)
        r.raise_for_status()
        times.append(time.time() - start)
    return times

def measure_rewrite_time(questions):
    times = []
    for q in questions:
        start = time.time()
        call_rewrite_llm(
            q["question"],
            "\n".join(q["options"]),
            q["wrong"],
            q["answer"]
        )
        times.append(time.time() - start)
    return times

if __name__ == "__main__":
    api_url = "http://127.0.0.1:8001/api/v1/rag/solve"

    print("=== 현재(해설만) API 속도 측정 ===")
    now_times = measure_api_time(api_url, questions)
    print(f"평균: {sum(now_times)/len(now_times):.3f}s, 최소: {min(now_times):.3f}s, 최대: {max(now_times):.3f}s")

    print("=== 옛날(rewrite 포함) 방식 속도 측정 ===")
    old_times = measure_rewrite_time(questions)
    print(f"평균: {sum(old_times)/len(old_times):.3f}s, 최소: {min(old_times):.3f}s, 최대: {max(old_times):.3f}s")
