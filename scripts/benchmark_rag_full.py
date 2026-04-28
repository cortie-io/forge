import time
import sys
sys.path.append(".")

from python_api.app.rag.engine import solve_items
from python_api.app.rag.models import ExamItem
from scripts.precompute_question_keywords import call_rewrite_llm

# 10개 샘플 문제 (실제 문제로 교체)
questions = [
    {
        "q": "다음 중 UDP에 대한 설명으로 가장 타당하지 않은 것은?",
        "opts": "UDP는 TCP에 비해 신뢰성이 떨어진다.\nUDP는 사용자 데이터그램(Datagram)이라고 하는 데이터 유니트를 송신지의 응용 프로세스에서 수신지의 응용 프로세스로 전송한다.\nUDP가 제공하는 오류검사는 홀수 패리티와 짝수 패리티가 있다.\nUDP가 제공하는 서비스는 비연결형 데이터 전달서비스(Compunctionless Data Delivery Service)이다.",
        "wrong": "",
        "ans": "UDP가 제공하는 오류검사는 홀수 패리티와 짝수 패리티가 있다."
    },
    # ... 9개 더 추가 ...
]

def solve_with_rewrite(items):
    patched = []
    for item in items:
        res = call_rewrite_llm(item["q"], item["opts"], item["wrong"], item["ans"])
        query = res.get("query", item["q"])
        patched.append(ExamItem(**{**item, "search_query": query}))
    return solve_items(patched, force_rebuild=True)

def solve_with_db(items):
    return solve_items([ExamItem(**item) for item in items], force_rebuild=True)

def measure(fn, items):
    times = []
    for _ in range(10):
        start = time.time()
        fn(items)
        times.append(time.time() - start)
    return times

if __name__ == "__main__":
    print("=== 전체 로직 + rewrite 포함 ===")
    t1 = measure(solve_with_rewrite, questions)
    print(f"평균: {sum(t1)/len(t1):.3f}s, 최소: {min(t1):.3f}s, 최대: {max(t1):.3f}s")

    print("=== 전체 로직 + DB 기반(현재) ===")
    t2 = measure(solve_with_db, questions)
    print(f"평균: {sum(t2)/len(t2):.3f}s, 최소: {min(t2):.3f}s, 최대: {max(t2):.3f}s")
