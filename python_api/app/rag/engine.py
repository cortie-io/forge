from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import List, Tuple

import pdfplumber
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import MarkdownHeaderTextSplitter

from ..settings import settings
from .models import EvidenceItem, SolveResult


# ─────────────────────────────────────────────
# 전역 싱글턴: 서버 시작 후 최초 1회만 로드
# ─────────────────────────────────────────────
_db: Chroma | None = None
_llm: ChatOllama | None = None


# ─────────────────────────────────────────────
# 데이터 보강 텍스트 (RAG/main.py 그대로)
# ─────────────────────────────────────────────
def _get_narrative_knowledge() -> str:
    return """
    ### [네트워크 관리사 2급 핵심 요약: 실무 및 누락 키워드 보강] ###
    - **리눅스 필수 명령어**: cp는 파일/디렉토리 복사, mv는 이동 및 이름 변경, rm은 삭제, grep은 파일 내 특정 문자열 검색, cat은 파일 내용 출력, vi는 텍스트 편집기를 의미합니다. netstat은 네트워크 연결 상태를 확인하며, umask는 파일 생성 시 기본 권한을 설정(777/666에서 umask 값을 뺀 값이 권한)합니다.
    - **네트워크 장비 및 스위칭**: L4 스위치는 IP/포트 기반 로드밸런싱을, L7 스위치는 URL/쿠키/데이터 기반 로드밸런싱을 수행합니다. 스위칭 방식 중 Cut-through는 목적지 주소만 확인 후 즉시 전송(가장 빠름), Store-and-forward는 전체 프레임을 저장 후 에러 체크(가장 신뢰성 높음)를 합니다. VLAN 간 통신을 위해선 트렁킹(Trunking, 802.1Q) 프로토콜이 필요합니다.
    - **라우팅 프로토콜 확장**: BGP는 자치 시스템(AS) 간 경로 정보를 교환하는 외부분과 경로 프로토콜(EGP)입니다. EIGRP는 Cisco 전용으로 거리 벡터와 링크 상태의 장점을 합친 하이브리드 프로토콜입니다.
    - **Windows Server 및 스토리지**: ReFS는 신축성 있는 파일 시스템으로 데이터 손상 방지가 뛰어납니다. Hyper-V는 가상화 기술이며, WAC(Windows Admin Center)는 웹 기반 통합 관리 도구입니다. RAID에서 0은 스트라이핑(속도), 1은 미러링(복구), 5는 패리티 분산 저장(성능+안정성)을 사용합니다.
    - **정보 보안**: PKI는 공개키 기반 구조로 인증서를 관리합니다. 보안 위협 중 스니핑은 엿듣기, 스푸핑은 속이기, 랜섬웨어는 데이터를 암호화 후 금전을 요구하는 공격입니다. 디지털 포렌식은 사고의 증거를 수집하는 기술입니다.
    """.strip()


_KEYWORDS = [
    "Active Directory", "chmod", "ifconfig", "OSPF", "RIP", "IPv6", "포트 번호", "방화벽", "ICMP",
    "umask", "netstat", "grep", "cp", "mv", "rm", "VLAN", "트렁킹", "RAID", "L4 스위치", "L7 스위치",
    "Cut-through", "BGP", "EIGRP", "ReFS", "WAC", "Hyper-V", "PKI", "랜섬웨어", "스니핑", "스푸핑",
]

_REWRITE_TEMPLATE = """
네트워크 관리사 2급 전문가로서, 교재 검색을 위한 최적의 쿼리를 생성하세요.
반드시 문제의 핵심 용어(예: umask, L4 스위치, BGP 등)를 포함해야 합니다.
JSON 응답: {{"query": "검색어 조합"}}
[문제]: {payload}
"""

_LEG_TEMPLATE = """
당신은 네트워크 관리사 2급 분야에서 가장 쉽고 친절하게 가르치는 '1타 강사'입니다. 
주어진 [지식 소스]의 내용을 바탕으로 학습자에게 전문적이면서도 다정한 해설을 제공하세요.

[필수 준수 규칙]
0. **[가장 중요]** [지식 소스]에만 근거하여 설명하세요. 개인적인 의견이나 외부 정보는 절대 포함하지 마세요.
    - [지식 소스]에 근거하여 설명한 후 부가 설명이 필요할 때만 뒤에 덧붙이세요.
    - [지식 소스]에서 근거를 찾지 못한 경우에만 문장 앞에 "[!]"를 붙이고 배경지식을 활용하세요.

1. 페르소나 및 금지어:
    - 친절한 구어체(~해요, ~예요)를 사용하고 "교재", "원문", "PDF", "근거", "데이터"라는 단어는 절대 사용하지 마세요.
    - 대신 "분석 결과에 따르면", "핵심 이론상", "네트워크 원리상" 등으로 대체하세요.

2. 상황별 맞춤 해설 로직:
    - **정답/오답 정보가 있는 경우**: 왜 그 보기가 정답이고, 사용자가 고른 보기는 어떤 점이 틀렸는지 비교 분석하세요.
    - **정답/오답 정보가 없는 경우("-")**: 당신이 직접 [지식 소스]를 바탕으로 문제를 풀어주세요.
    - **body > correction**: 오답이 있으면 '비교 분석', 없으면 '문제의 핵심 함정이나 주의사항'을 설명하세요.
    - **body > answer**: 제공된 정답이 있으면 그 정답을 넣고, 정답이 "-"라면 당신이 도출한 '최종 정답 번호와 보기 내용'을 명확히 적으세요.

3. 에비던스 정제 및 가독성:
    - audit > refined_evidence에는 사실 관계 변경 없이 문장만 다듬어서 넣으세요.
    - **표(Table)** 데이터는 반드시 이해하기 쉬운 **서술형 문장**으로 풀어서 설명하세요.

지식 소스: {context}
문제 데이터: {question}

JSON 응답:
{{
  "header": {{ "ans": "정답 번호", "keyword": "핵심 키워드", "level": "난이도" }},
  "body": {{
    "overview": "이론적 배경 설명 (강사의 말투로 부드럽게)",
    "analysis": {{ 
      "1": "보기1 상세 분석", 
      "2": "보기2 상세 분석", 
      "3": "보기3 상세 분석", 
      "4": "보기4 상세 분석" 
    }},
    "correction": "상황별 맞춤 보충 설명 (오답 분석 또는 함정 탈출법)",
    "insight": "직관적인 개념 비유",
    "answer": "제공된 정답 혹은 AI가 도출한 최종 정답"
  }},
  "audit": {{ 
    "evidence_ids": [번호], 
    "source": "공식 학습 이론",
    "refined_evidence": [
      {{ "id": 번호, "text": "내용 유지/표는 서술형/문장 정제된 원문" }}
    ]
  }},
  "magic_tip": "시험장에서 바로 써먹는 암기 꿀팁"
}}
"""


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def _clean_text(text: str) -> str:
    text = re.sub(r"[一-龥ぁ-ゔァ-ヴー]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            return {"error": "JSON_PARSE_FAILED"}
    return {"error": "NO_JSON_FOUND"}


# ─────────────────────────────────────────────
# DB 빌드 (DB 없을 때만 실행)
# ─────────────────────────────────────────────
def _build_db(force: bool = False) -> Chroma:
    db_dir = settings.CHROMA_DB_DIR
    md_path = settings.MD_PATH
    pdf_path = settings.PDF_PATH

    if not force and os.path.exists(db_dir):
        print(f"[RAG] 기존 벡터 DB 재사용: {db_dir}")
        embeddings = OllamaEmbeddings(model=settings.OLLAMA_EMBED_MODEL, base_url=settings.OLLAMA_HOST)
        return Chroma(persist_directory=db_dir, embedding_function=embeddings)

    print("[RAG] 벡터 DB 빌드 시작...")

    with open(md_path, "r", encoding="utf-8") as f:
        existing_md = f.read()

    supplement_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                cleaned = _clean_text(page_text)
                for kw in _KEYWORDS:
                    if kw.lower() in cleaned.lower():
                        cleaned = f"\n### {kw} 상세 기술 정보\n" + cleaned
                supplement_text += cleaned + "\n\n"

    full_text = f"{_get_narrative_knowledge()}\n\n{existing_md}\n\n# PDF 상세 보강 데이터\n{supplement_text}"

    headers_to_split_on = [("#", "Subject"), ("##", "Chapter"), ("###", "Section")]
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    splits = splitter.split_text(full_text)

    embeddings = OllamaEmbeddings(model=settings.OLLAMA_EMBED_MODEL, base_url=settings.OLLAMA_HOST)

    if os.path.exists(db_dir):
        shutil.rmtree(db_dir)

    db = Chroma.from_documents(documents=splits, embedding=embeddings, persist_directory=db_dir)
    print(f"[RAG] 벡터 DB 빌드 완료: {len(splits)}개 청크")
    return db


# ─────────────────────────────────────────────
# 싱글턴 접근자
# ─────────────────────────────────────────────
def get_db(force_rebuild: bool = False) -> Chroma:
    global _db
    if _db is None or force_rebuild:
        _db = _build_db(force=force_rebuild)
    return _db


def get_llm() -> ChatOllama:
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.OLLAMA_MODEL, base_url=settings.OLLAMA_HOST, temperature=0)
    return _llm


# ─────────────────────────────────────────────
# 메인 풀이 로직
# ─────────────────────────────────────────────
def solve_items(
    items: list,
    force_rebuild: bool = False,
) -> List[SolveResult]:
    db = get_db(force_rebuild=force_rebuild)
    llm = get_llm()
    results: List[SolveResult] = []

    for i, item in enumerate(items):
        print(f"[RAG] [{i+1}/{len(items)}] 분석 중: {item.q[:30]}...")
        payload = f"문제: {item.q}\n보기: {item.opts}\n오답: {item.wrong}\n정답: {item.ans}"

        rewrite_res = llm.invoke(_REWRITE_TEMPLATE.format(payload=payload))
        search_query = _extract_json(rewrite_res.content).get("query", item.q)

        docs = db.as_retriever(
            search_type="mmr",
            search_kwargs={"k": 12, "lambda_mult": 0.4},
        ).invoke(search_query)

        context_text = "\n\n".join([f"[{j+1}] {d.page_content}" for j, d in enumerate(docs)])
        final_res = llm.invoke(_LEG_TEMPLATE.format(context=context_text, question=payload))

        results.append(
            SolveResult(
                report=_extract_json(final_res.content),
                evidence=[
                    EvidenceItem(id=j + 1, text=d.page_content)
                    for j, d in enumerate(docs)
                ],
            )
        )
        time.sleep(0.5)

    return results
