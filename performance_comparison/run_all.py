from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List


def run(cmd: List[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="sample_120_questions.csv")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--model", default="gemma4-e4b:latest")
    p.add_argument("--ollama-host", default="http://100.79.44.109:11434")
    p.add_argument("--api-base", default="http://127.0.0.1:8001")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--judge-model", default="gpt-4o")
    p.add_argument("--judge-timeout", type=int, default=120)
    p.add_argument("--require-judge", type=int, default=1)
    p.add_argument("--raw-structure", default="../refs/structure/network_structure.json")
    args = p.parse_args()

    os.makedirs("results", exist_ok=True)

    py = sys.executable
    run(
        [
            py,
            "gemma_only.py",
            "--input",
            args.input,
            "--output",
            "results/gemma_only_results.csv",
            "--model",
            args.model,
            "--host",
            args.ollama_host,
            "--limit",
            str(args.limit),
            "--timeout",
            str(args.timeout),
        ]
    )
    run(
        [
            py,
            "rag_with_gemma.py",
            "--input",
            args.input,
            "--output",
            "results/rag_with_gemma_results.csv",
            "--model",
            args.model,
            "--ollama-host",
            args.ollama_host,
            "--api-base",
            args.api_base,
            "--limit",
            str(args.limit),
            "--timeout",
            str(args.timeout),
        ]
    )
    run(
        [
            py,
            "full_pipeline.py",
            "--input",
            args.input,
            "--output",
            "results/full_pipeline_results.csv",
            "--api-base",
            args.api_base,
            "--limit",
            str(args.limit),
            "--timeout",
            str(args.timeout),
        ]
    )

    run([
        py,
        "evaluation.py",
        "--input",
        "results/gemma_only_results.csv",
        "--output",
        "results/gemma_only_evaluated.csv",
        "--group",
        "A (LLM-only)",
        "--judge-model",
        args.judge_model,
        "--judge-timeout",
        str(args.judge_timeout),
        "--require-judge",
        str(args.require_judge),
        "--raw-structure",
        args.raw_structure,
    ])
    run([
        py,
        "evaluation.py",
        "--input",
        "results/rag_with_gemma_results.csv",
        "--output",
        "results/rag_with_gemma_evaluated.csv",
        "--group",
        "B (Naive RAG)",
        "--judge-model",
        args.judge_model,
        "--judge-timeout",
        str(args.judge_timeout),
        "--require-judge",
        str(args.require_judge),
        "--raw-structure",
        args.raw_structure,
    ])
    run([
        py,
        "evaluation.py",
        "--input",
        "results/full_pipeline_results.csv",
        "--output",
        "results/full_pipeline_evaluated.csv",
        "--group",
        "C (Full Pipeline)",
        "--judge-model",
        args.judge_model,
        "--judge-timeout",
        str(args.judge_timeout),
        "--require-judge",
        str(args.require_judge),
        "--raw-structure",
        args.raw_structure,
    ])

    run([py, "performance_analysis.py"])
    print("[done] benchmark pipeline completed")


if __name__ == "__main__":
    main()
