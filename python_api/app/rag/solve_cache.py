
"""
문항 단위 RAG 해설 캐시 모듈
 - 메모리 LRU + 디스크(JSON) 캐시로 프로세스 재시작 후에도 캐시 히트 가능
 - 환경변수로 용량/TTL/경로/활성화 제어
 - thread-safe, 예외 안전, 엔터프라이즈 품질
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


# 메모리 LRU: 0이면 비활성
_MAX_MEM = max(0, _env_int("RAG_SOLVE_CACHE_MAX", 400))
_TTL_SEC = float(os.getenv("RAG_SOLVE_CACHE_TTL_SEC", str(86400)))

# 디스크: 기본 활성, python_api/.rag_solve_cache
_DISK_ENABLED = _env_bool("RAG_SOLVE_DISK_CACHE", True)
_DISK_MAX_FILES = max(0, _env_int("RAG_SOLVE_DISK_CACHE_MAX", 2000))
_DEFAULT_DISK_DIR = Path(__file__).resolve().parents[2] / ".rag_solve_cache"
_DISK_DIR = Path(os.getenv("RAG_SOLVE_CACHE_DIR", str(_DEFAULT_DISK_DIR))).expanduser()
_SAFE_KEY_RE = re.compile(r"^[a-f0-9]{64}$")


class _SolveResultLRU:
    """
    Thread-safe LRU 캐시 (TTL 지원)
    - get: 만료된 항목 자동 제거
    - set: 용량 초과 시 LRU pop
    """
    def __init__(self, max_entries: int, ttl_sec: float) -> None:
        self._max = max_entries
        self._ttl = ttl_sec
        self._store: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """key에 해당하는 payload 반환 (만료 시 None)"""
        now = time.time()
        with self._lock:
            ent = self._store.get(key)
            if ent is None:
                return None
            exp, payload = ent
            if exp < now:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return copy.deepcopy(payload)

    def set(self, key: str, payload: dict[str, Any]) -> None:
        """key에 payload 저장 (만료시간 적용, LRU pop)"""
        if self._max <= 0:
            return
        now = time.time()
        with self._lock:
            self._store[key] = (now + self._ttl, copy.deepcopy(payload))
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)


_MEM: Optional[_SolveResultLRU] = None
if _MAX_MEM > 0:
    _MEM = _SolveResultLRU(_MAX_MEM, _TTL_SEC)

_disk_lock = threading.Lock()


def _disk_path(key: str) -> Path:
    """SHA256 64자 key만 허용, 디스크 캐시 경로 반환"""
    if not _SAFE_KEY_RE.match(key):
        raise ValueError("invalid cache key")
    return _DISK_DIR / f"{key}.json"


def _disk_prune() -> None:
    """디스크 캐시 파일 개수 제한 초과 시 LRU 삭제"""
    if _DISK_MAX_FILES <= 0:
        return
    try:
        files = [p for p in _DISK_DIR.glob("*.json") if p.is_file()]
    except OSError:
        return
    if len(files) <= _DISK_MAX_FILES:
        return
    files.sort(key=lambda p: p.stat().st_mtime)
    for p in files[: max(0, len(files) - _DISK_MAX_FILES)]:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _disk_get(key: str) -> Optional[dict[str, Any]]:
    """디스크 캐시에서 key 조회 (만료/오류/비활성화 시 None)"""
    if not _DISK_ENABLED or _DISK_MAX_FILES <= 0:
        return None
    path = _disk_path(key)
    with _disk_lock:
        try:
            if not path.is_file():
                return None
            raw = path.read_text(encoding="utf-8")
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                return None
            exp = float(obj.get("_exp", 0))
            if exp < time.time():
                path.unlink(missing_ok=True)
                return None
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                return None
            return copy.deepcopy(payload)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None


def _disk_set(key: str, payload: dict[str, Any]) -> None:
    """디스크 캐시에 key/payload 저장 (atomic, 예외 안전)"""
    if not _DISK_ENABLED or _DISK_MAX_FILES <= 0:
        return
    _DISK_DIR.mkdir(parents=True, exist_ok=True)
    path = _disk_path(key)
    wrapper = {"_exp": time.time() + _TTL_SEC, "payload": copy.deepcopy(payload)}
    data = json.dumps(wrapper, ensure_ascii=False)
    tmp_path: Optional[str] = None
    with _disk_lock:
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="rc_", suffix=".json", dir=str(_DISK_DIR))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, path)
            tmp_path = None
        except OSError:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            return
        _disk_prune()


def solve_cache_key(item: Any) -> str:
    """
    ExamItem 호환: 주요 필드 정규화 후 SHA256 해시 반환
    - 동일 문제/보기/정답/오답 조합은 항상 동일 key
    """
    raw = {
        "q": str(getattr(item, "q", "") or "").strip(),
        "opts": str(getattr(item, "opts", "") or "").strip(),
        "wrong": str(getattr(item, "wrong", "") or "").strip(),
        "ans": str(getattr(item, "ans", "") or "").strip(),
        "search_query": str(getattr(item, "search_query", "") or "").strip(),
        "user_message": str(getattr(item, "user_message", "") or "").strip(),
        "ontology_subject": str(getattr(item, "ontology_subject", "") or "").strip(),
        "ontology_chapter": str(getattr(item, "ontology_chapter", "") or "").strip(),
        "ontology_concept": str(getattr(item, "ontology_concept", "") or "").strip(),
        "ontology_coordinates": getattr(item, "ontology_coordinates", None),
    }
    blob = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def solve_cache_get(key: str) -> Optional[dict[str, Any]]:
    """
    key에 해당하는 캐시 payload 반환 (메모리→디스크 순, 만료/미존재 시 None)
    - 디스크 hit 시 메모리 LRU에도 적재
    """
    if _MEM is not None:
        hit = _MEM.get(key)
        if hit is not None:
            return hit
    disk = _disk_get(key)
    if disk is not None and _MEM is not None:
        _MEM.set(key, disk)
    return disk


def solve_cache_set(key: str, payload: dict[str, Any]) -> None:
    """
    key에 payload를 캐시 저장 (메모리 LRU, 디스크 모두)
    """
    if _MEM is not None:
        _MEM.set(key, payload)
    _disk_set(key, payload)
