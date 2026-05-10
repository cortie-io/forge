#!/usr/bin/env python3
"""
자동 평가 감시 스크립트
- 3개 Group 프로세스 완료 대기
- CSV 파일 완성 확인
- 평가 및 분석 스크립트 자동 실행
"""

import os
import sys
import time
import subprocess
import psutil
from pathlib import Path

def wait_for_processes():
    """Group 프로세스 완료 대기"""
    print("\n[감시] Group A, B, C 프로세스 완료 대기 중...")
    
    while True:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else ''
                if any(x in cmdline for x in ['gemma_only.py', 'rag_with_gemma.py', 'full_pipeline.py']):
                    processes.append((proc.pid, proc.name()))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not processes:
            print("[완료] 모든 Group 프로세스 종료됨 ✓")
            return
        
        print(f"[진행] 실행 중인 프로세스: {len(processes)}개", end='\r')
        time.sleep(5)

def check_csv_completion():
    """CSV 파일 완성도 확인"""
    print("\n[확인] CSV 파일 완성도 검증 중...")
    
    csv_files = [
        'results/gemma_only_results.csv',
        'results/rag_with_gemma_results.csv',
        'results/full_pipeline_results.csv'
    ]
    
    for csv_file in csv_files:
        if not os.path.exists(csv_file):
            print(f"  ✗ {csv_file}: 파일 없음")
            return False
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            rows = len(lines) - 1  # 헤더 제외
            if rows < 120:
                print(f"  ✗ {csv_file}: {rows}/120 행만 완성")
                return False
            print(f"  ✓ {csv_file}: {rows} 행 완성")
    
    return True

def run_evaluation(api_key):
    """평가 스크립트 실행"""
    print("\n[평가] evaluation.py 실행 중...\n")
    
    env = os.environ.copy()
    env['OPENAI_API_KEY'] = api_key
    
    py = sys.executable
    result = subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/gemma_only_results.csv',
        '--output', 'results/gemma_only_evaluated.csv',
        '--group', 'A (LLM-only)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    if result.returncode != 0:
        print(f"✗ Group A 평가 실패 (exit code: {result.returncode})")
        return False
    
    result = subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/rag_with_gemma_results.csv',
        '--output', 'results/rag_with_gemma_evaluated.csv',
        '--group', 'B (Naive RAG)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    if result.returncode != 0:
        print(f"✗ Group B 평가 실패 (exit code: {result.returncode})")
        return False
    
    result = subprocess.run([
        py, 'evaluation.py',
        '--input', 'results/full_pipeline_results.csv',
        '--output', 'results/full_pipeline_evaluated.csv',
        '--group', 'C (Full Pipeline)',
        '--judge-model', 'gpt-4o-mini',
        '--judge-timeout', '120',
        '--require-judge', '1'
    ], env=env)
    
    if result.returncode != 0:
        print(f"✗ Group C 평가 실패 (exit code: {result.returncode})")
        return False
    
    print("\n✓ 평가 완료")
    return True

def run_analysis():
    """분석 및 보고서 생성"""
    print("\n[분석] performance_analysis.py 실행 중...\n")
    
    py = sys.executable
    result = subprocess.run([
        py, 'performance_analysis.py'
    ])
    
    if result.returncode != 0:
        print(f"✗ 분석 실패 (exit code: {result.returncode})")
        return False
    
    print("\n✓ 분석 완료")
    return True

def main():
    print("=" * 60)
    print("자동 평가 감시 스크립트 시작")
    print("=" * 60)
    
    # API 키 확인
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("✗ OPENAI_API_KEY 환경변수가 설정되지 않음")
        sys.exit(1)
    
    # Group 프로세스 완료 대기
    wait_for_processes()
    
    # CSV 완성도 검증
    if not check_csv_completion():
        print("✗ CSV 파일 미완성, 평가 중단")
        sys.exit(1)
    
    # 평가 실행
    if not run_evaluation(api_key):
        print("✗ 평가 실패")
        sys.exit(1)
    
    # 분석 실행
    if not run_analysis():
        print("✗ 분석 실패")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✓ 모든 작업 완료!")
    print("=" * 60)
    print("\n결과 파일:")
    print("  - results/gemma_only_evaluated.csv")
    print("  - results/rag_with_gemma_evaluated.csv")
    print("  - results/full_pipeline_evaluated.csv")
    print("  - results/performance_summary.csv")
    print("  - results/experiment_report.md")

if __name__ == '__main__':
    main()
