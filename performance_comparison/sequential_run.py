#!/usr/bin/env python3
"""
순차 실행 관리 스크립트
- Group A 완료 대기
- Group B 시작 및 완료 대기
- Group C 시작 및 완료 대기
- 자동 평가 및 분석 실행
"""

import os
import sys
import time
import subprocess
import psutil
from pathlib import Path

def wait_for_process(process_name):
    """특정 프로세스 완료 대기"""
    while True:
        found = False
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else ''
                if process_name in cmdline:
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not found:
            return
        time.sleep(2)

def check_csv_completed(csv_file, expected_rows=120):
    """CSV 파일 완성 여부 확인"""
    if not os.path.exists(csv_file):
        return False
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            rows = len(lines) - 1  # 헤더 제외
            return rows >= expected_rows
    except:
        return False

def run_group(name, py_file, args, timeout_sec):
    """Group 실행"""
    print(f"\n{'='*60}")
    print(f"[시작] {name}")
    print(f"{'='*60}\n")
    
    py = sys.executable
    start_time = time.time()
    
    result = subprocess.run(
        [py, py_file] + args,
        capture_output=False
    )
    
    elapsed = time.time() - start_time
    elapsed_min = int(elapsed / 60)
    elapsed_sec = int(elapsed % 60)
    
    print(f"\n[완료] {name} - 소요시간: {elapsed_min}분 {elapsed_sec}초")
    
    return result.returncode == 0

def main():
    print("\n" + "="*60)
    print("순차 실행 관리 스크립트")
    print("="*60)
    
    os.chdir('/home/ubuntu/forge/performance_comparison')
    
    # API 키 확인
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("✗ OPENAI_API_KEY 환경변수 필요")
        sys.exit(1)
    
    # Group A 완료 대기 (이미 실행 중)
    print("\n[대기] Group A 완료 대기 중...")
    wait_for_process('gemma_only.py')
    
    if not check_csv_completed('results/gemma_only_results.csv'):
        print("✗ Group A CSV 미완성")
        sys.exit(1)
    print("✓ Group A 완료")
    
    # Group B 실행
    success = run_group(
        "Group B (Naive RAG)",
        "rag_with_gemma.py",
        [
            "--input", "sample_120_questions.csv",
            "--output", "results/rag_with_gemma_results.csv",
            "--model", "gemma4-e4b:latest",
            "--ollama-host", "http://100.79.44.109:11434",
            "--api-base", "http://127.0.0.1:8001",
            "--timeout", "300"
        ],
        300
    )
    
    if not success or not check_csv_completed('results/rag_with_gemma_results.csv'):
        print("✗ Group B 실패")
        sys.exit(1)
    print("✓ Group B 완료")
    
    # Group C 실행
    success = run_group(
        "Group C (Full Pipeline)",
        "full_pipeline.py",
        [
            "--input", "sample_120_questions.csv",
            "--output", "results/full_pipeline_results.csv",
            "--api-base", "http://127.0.0.1:8001",
            "--timeout", "300"
        ],
        300
    )
    
    if not success or not check_csv_completed('results/full_pipeline_results.csv'):
        print("✗ Group C 실패")
        sys.exit(1)
    print("✓ Group C 완료")
    
    # 평가 실행
    print("\n" + "="*60)
    print("[평가] 시작")
    print("="*60 + "\n")
    
    env = os.environ.copy()
    env['OPENAI_API_KEY'] = api_key
    
    py = sys.executable
    
    # Group A 평가
    subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/gemma_only_results.csv',
        '--output', 'results/gemma_only_evaluated.csv',
        '--group', 'A (LLM-only)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    # Group B 평가
    subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/rag_with_gemma_results.csv',
        '--output', 'results/rag_with_gemma_evaluated.csv',
        '--group', 'B (Naive RAG)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    # Group C 평가
    subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/full_pipeline_results.csv',
        '--output', 'results/full_pipeline_evaluated.csv',
        '--group', 'C (Full Pipeline)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    # 분석 실행
    print("\n" + "="*60)
    print("[분석] 시작")
    print("="*60 + "\n")
    
    subprocess.run([py, 'performance_analysis.py'])
    
    print("\n" + "="*60)
    print("✓ 모든 작업 완료!")
    print("="*60)
    print("\n최종 결과 파일:")
    print("  - results/performance_summary.csv")
    print("  - results/experiment_report.md")

if __name__ == '__main__':
    main()
