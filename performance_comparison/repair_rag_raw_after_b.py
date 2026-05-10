#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import shutil
import time
from datetime import datetime
from typing import Dict, Any

import psutil


RAW_PATH = "results/rag_with_gemma_results_raw.jsonl"
CSV_PATH = "results/rag_with_gemma_results.csv"


def is_b_running() -> bool:
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "rag_with_gemma.py" in cmdline:
            return True
    return False


def read_csv_by_index(path: str) -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(path):
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            idx_raw = row.get("index", "").strip()
            if not idx_raw:
                continue
            try:
                idx = int(float(idx_raw))
            except ValueError:
                continue
            out[idx] = row
    return out


def repair_raw(raw_path: str, csv_path: str) -> None:
    if not os.path.exists(raw_path):
        print(f"[SKIP] raw file not found: {raw_path}")
        return

    csv_map = read_csv_by_index(csv_path)

    valid_by_index: Dict[int, Dict[str, Any]] = {}
    bad_lines = 0

    with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                bad_lines += 1
                continue
            try:
                obj = json.loads(s)
            except Exception:
                bad_lines += 1
                continue

            idx = obj.get("index")
            try:
                idx = int(idx)
            except Exception:
                bad_lines += 1
                continue

            # Keep first valid occurrence.
            if idx not in valid_by_index:
                valid_by_index[idx] = obj

    if not valid_by_index and not csv_map:
        print("[SKIP] no usable data found in raw/csv")
        return

    max_idx = max(list(valid_by_index.keys()) + list(csv_map.keys()))

    rebuilt = []
    recovered_count = 0
    for idx in range(1, max_idx + 1):
        if idx in valid_by_index:
            rebuilt.append(valid_by_index[idx])
            continue

        csv_row = csv_map.get(idx)
        if csv_row is not None:
            rebuilt.append(
                {
                    "index": idx,
                    "raw_response": "",
                    "evidence_docs": [],
                    "parsed": csv_row,
                    "recovered": True,
                    "recovery_reason": "missing_or_broken_raw_line_filled_from_csv",
                }
            )
        else:
            rebuilt.append(
                {
                    "index": idx,
                    "raw_response": "",
                    "evidence_docs": [],
                    "parsed": {
                        "mode": "naive_rag",
                        "index": idx,
                        "AI_정답": "",
                        "is_correct": 0,
                        "error": "RECOVERED_MISSING_JSONL_LINE_NO_CSV",
                    },
                    "recovered": True,
                    "recovery_reason": "missing_or_broken_raw_line_no_csv",
                }
            )
        recovered_count += 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{raw_path}.bak_{timestamp}"
    shutil.copy2(raw_path, backup_path)

    tmp_path = f"{raw_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        for obj in rebuilt:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    os.replace(tmp_path, raw_path)

    print(f"[DONE] repaired raw file: {raw_path}")
    print(f"[INFO] backup: {backup_path}")
    print(f"[INFO] valid_lines={len(valid_by_index)} bad_lines={bad_lines} recovered={recovered_count} final_rows={len(rebuilt)}")


def main() -> None:
    print("[WAIT] waiting for rag_with_gemma.py to finish...")
    while is_b_running():
        time.sleep(5)

    # Small delay to ensure the writer fully flushes and exits.
    time.sleep(2)

    repair_raw(RAW_PATH, CSV_PATH)


if __name__ == "__main__":
    main()
