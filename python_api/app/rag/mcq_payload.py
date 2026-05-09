"""
사용자 자유 텍스트에서 4지선다 형태를 추출해 ExamItem 구성에 사용합니다.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel


def _parse_option_lines(lines: List[str]) -> Optional[List[str]]:
    opts_found: List[Tuple[int, str]] = []
    pat_line = re.compile(r"^\s*([1-4])[\.\)]\s*(.+)$")
    for line in lines:
        clean = str(line or "").strip()
        if not clean:
            continue
        m = pat_line.match(clean)
        if m:
            opts_found.append((int(m.group(1)), m.group(2).strip()))
    if len(opts_found) != 4:
        return None
    nums = sorted(n for n, _ in opts_found)
    if nums != [1, 2, 3, 4]:
        return None
    opts = [text for _, text in sorted(opts_found, key=lambda item: item[0])]
    return opts if all(opts) else None


def parse_mcq_payload_details(text: str) -> Optional[Dict[str, Any]]:
    """
    구조화된 문제 payload를 파싱합니다.
    지원 예시:
    [사용자 메시지]
    이 문제 풀이해줘
    [문제]
    ...
    [보기]
    1) ...
    2) ...
    3) ...
    4) ...
    [오답]
    2
    [정답]
    4
    """
    t = str(text or "").strip()
    if not t:
        return None

    section_pat = re.compile(
        r"(?ms)^\[(사용자 메시지|문제|보기|오답|정답)\]\s*$\n?(.*?)(?=^\[(?:사용자 메시지|문제|보기|오답|정답)\]\s*$|\Z)"
    )
    sections: Dict[str, str] = {}
    for label, body in section_pat.findall(t):
        sections[str(label).strip()] = str(body or "").strip()

    if not sections:
        return None

    stem = sections.get("문제", "").strip()
    opts = _parse_option_lines((sections.get("보기", "") or "").splitlines())
    if not stem or not opts:
        return None

    wrong = sections.get("오답", "").strip() or "-"
    ans = sections.get("정답", "").strip() or "-"
    user_message = sections.get("사용자 메시지", "").strip()
    return {
        "stem": stem,
        "opts": opts,
        "wrong": wrong,
        "ans": ans,
        "user_message": user_message,
    }


def parse_mcq_from_payload(text: str) -> Optional[Tuple[str, List[str]]]:
    """
    (문제 본문, 보기 4개 문자열) 또는 파싱 불가 시 None.
    지원: ①②③④ 구분, 줄 시작의 1)~4) / 1.~4. 패턴.
    """
    t = str(text or "").strip()
    if not t:
        return None

    structured = parse_mcq_payload_details(t)
    if structured:
        return structured["stem"], structured["opts"]

    if all(ch in t for ch in "①②③④"):
        parts = re.split(r"[①②③④]", t)
        if len(parts) >= 5:
            stem = parts[0].strip()
            opts = [parts[i].strip() for i in range(1, 5)]
            if stem and all(len(o.strip()) > 0 for o in opts):
                return stem, opts

    lines = [ln.rstrip() for ln in t.splitlines()]
    stem_lines: List[str] = []
    pat_line = re.compile(r"^\s*([1-4])[\.\)]\s*(.+)$")
    opts_found: List[Tuple[int, str]] = []
    for line in lines:
        if not line.strip():
            continue
        m = pat_line.match(line.strip())
        if m:
            opts_found.append((int(m.group(1)), m.group(2).strip()))
        elif not opts_found:
            stem_lines.append(line.strip())
    if len(opts_found) == 4:
        nums = sorted(n for n, _ in opts_found)
        if nums == [1, 2, 3, 4]:
            stem = "\n".join(x for x in stem_lines if x is not None).strip()
            opts_ordered = [t for _, t in sorted(opts_found, key=lambda x: x[0])]
            if stem and all(len(o) > 0 for o in opts_ordered):
                return stem, opts_ordered

    return None


def format_opts_for_exam_item(opts: List[str]) -> str:
    return ", ".join(f"{i + 1}) {o}" for i, o in enumerate(opts))


def format_leg_report_for_chat(report: Dict[str, Any]) -> str:
    """Problem Explain LEG JSON → 채팅용 플레인 텍스트."""
    if not isinstance(report, dict):
        return "해설 결과를 표시할 수 없습니다."
    lines: List[str] = []
    header = report.get("header") or {}
    if isinstance(header, dict):
        kw = str(header.get("keyword", "") or "").strip()
        lvl = str(header.get("level", "") or "").strip()
        if kw or lvl:
            meta = " · ".join(x for x in [f"키워드: {kw}" if kw else "", f"난이도: {lvl}" if lvl else ""] if x)
            if meta:
                lines.append(meta)
    body = report.get("body") or {}
    if isinstance(body, dict):
        ov = str(body.get("overview", "") or "").strip()
        if ov:
            lines.append(ov)
        analysis = body.get("analysis") or {}
        if isinstance(analysis, dict) and analysis:
            lines.append("")
            for k in sorted(analysis.keys(), key=lambda x: str(x)):
                lines.append(f"〔보기 {k}〕 {analysis[k]}")
        corr = str(body.get("correction", "") or "").strip()
        if corr:
            lines.append("")
            lines.append(f"오답·함정: {corr}")
        ins = str(body.get("insight", "") or "").strip()
        if ins:
            lines.append("")
            lines.append(f"직관: {ins}")
        ans = str(body.get("answer", "") or "").strip()
        if ans:
            lines.append("")
            lines.append(f"정리: {ans}")
    tip = str(report.get("magic_tip", "") or "").strip()
    if tip:
        lines.append("")
        lines.append(f"💡 시험 팁: {tip}")
    out = "\n".join(lines).strip()
    return out if out else "해설이 생성되었으나 본문이 비어 있습니다."


def build_exam_item_for_leg(
    payload: str,
    analysis: BaseModel,
    stem: str,
    opts: List[str],
    *,
    wrong: str = "-",
    ans: str = "-",
    user_message: str = "",
) -> Any:
    from .models import ExamItem

    coord = getattr(analysis, "coordinate", None)
    subject = getattr(coord, "subject", "") if coord else ""
    chapter = getattr(coord, "chapter", "") if coord else ""
    concept = getattr(coord, "concept", "") if coord else ""

    coords_raw = getattr(analysis, "coordinates", None) or []
    ontology_coordinates = []
    if isinstance(coords_raw, list):
        for c in coords_raw:
            if hasattr(c, "model_dump"):
                ontology_coordinates.append(c.model_dump())
            elif isinstance(c, dict):
                ontology_coordinates.append(
                    {
                        "subject": str(c.get("subject", "") or ""),
                        "chapter": str(c.get("chapter", "") or ""),
                        "concept": str(c.get("concept", "") or ""),
                    }
                )

    sq = str(getattr(analysis, "search_query", "") or "").strip() or stem

    return ExamItem(
        q=stem,
        opts=format_opts_for_exam_item(opts),
        wrong=str(wrong or "-").strip() or "-",
        ans=str(ans or "-").strip() or "-",
        search_query=sq,
        user_message=(str(user_message).strip() or str(payload).strip())[:4000] or None,
        ontology_subject=str(subject).strip() or None,
        ontology_chapter=str(chapter).strip() or None,
        ontology_concept=str(concept).strip() or None,
        ontology_coordinates=ontology_coordinates or None,
    )


def try_build_exam_item_for_explain_problem(payload: str, analysis: BaseModel) -> Optional[Any]:
    details = parse_mcq_payload_details(payload)
    if details:
        return build_exam_item_for_leg(
            payload,
            analysis,
            details["stem"],
            details["opts"],
            wrong=details["wrong"],
            ans=details["ans"],
            user_message=details["user_message"],
        )

    parsed = parse_mcq_from_payload(payload)
    if not parsed:
        return None
    stem, opts = parsed
    return build_exam_item_for_leg(payload, analysis, stem, opts)
