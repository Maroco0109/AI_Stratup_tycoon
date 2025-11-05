"""
Strict prompt helpers to make gpt-4o-mini event cards concrete and scoring criteria explicit.

These functions are imported by engine_openai.py and override the issuer/tester prompts
to produce specific incident-driven event cards and score for problem-solution fit.
"""

from __future__ import annotations

from typing import Any, Dict, List

from prompts.templates import input_guidelines, RUBRIC_BY_DAY  # type: ignore

# 한국어 설명
# - 이 모듈은 OpenAI 전용 엔진에서 사용할 "엄격한 프롬프트" 빌더를 제공합니다.
# - 발행자(EEVE 역할 헤더)와 채점자(OpenAI 역할 헤더)의 스키마/톤/금지 사항을 명시적으로 안내하여
#   모델이 한 번에 하나의 ```json 펜스 블록만 출력하도록 유도합니다.


def _issuer_system_prompt_strict(day: int, mode: str) -> str:
    guideline = input_guidelines(day) or ""
    base = (
        "Follow these strict rules.\n"
        "- Output exactly one JSON object inside a single ```json fenced block.\n"
        "- No pre/post text, markdown, emojis, comments, or repetition.\n"
        "- Header keys: version=\\\"AST-v1\\\", role=\\\"EEVE\\\", day.\n"
        "- Use Korean polite tone only inside JSON string values.\n"
        "- Do NOT score or mention delta/score. EEVE never scores.\n"
        "- Observe the following user input guideline:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "Schema: type=\\\"event_card\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- Generate a concrete incident (NOT a discussion topic). State a specific problem that actually occurred.\n"
            "- The summary MUST include measurable details: endpoint/component, metric deviation with numbers (e.g., p95 +40% or HTTP 500-rate 18%), timeframe, user segment/env, and any error code or log clue. Keep it to 1-2 sentences.\n"
            "- eval_focus: 3 concise items covering (1) root-cause alignment, (2) actionability (immediate/short/mid), (3) safety & measurement.\n"
            "- response_instructions: Ask the user to propose a one-paragraph fix plan for this incident.\n"
            "- constraints: include '한 문단으로만 작성', '한국어 존댓말 사용'.\n"
            "- Do not provide answers or analysis; only output the card JSON.\n"
        )
    return base + (
        "Schema: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- Write 1-2 sentences each. No lists/line breaks.\n"
        "- No scores, grades, or numeric deltas.\n"
    )


def _issuer_event_payload_strict(day: int) -> str:
    return (
        "Produce an event_card(JSON) for the given day.\n"
        f"- Day: {day}\n"
        "- Require a specific incident, not a vague discussion. It must name a component/endpoint, quantify impact (metric delta, error rate), give a timeframe and environment, and cite any error code/log clue.\n"
        "- response_instructions must ask the user for a one-paragraph fix plan for this incident (immediate/short/mid actions).\n"
        "- constraints must include: '한 문단으로만 작성', '한국어 존댓말 사용'.\n"
        "- Required keys: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )


def _tester_system_prompt_strict(day: int) -> str:
    rubric = RUBRIC_BY_DAY.get(day, "")
    return (
        "Return exactly one JSON object (no extra text) in a ```json fenced block.\n"
        "Header: version=\"AST-v1\", role=\"OpenAI\", type=\"daily_score\", day.\n"
        "Keys: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "Scoring focus: Evaluate whether the user's one-paragraph plan appropriately fixes the specific incident in the event card. Consider (1) problem-solution fit/root-cause alignment, (2) actionability (immediate/short/mid), (3) safety & measurement (rollback, comms, monitoring). Penalize vague, off-target, or non-actionable answers.\n"
        f"{rubric}"
    )


# --- Appended overrides to tune specificity and difficulty ------------------

def _issuer_system_prompt_strict(day: int, mode: str) -> str:  # type: ignore[override]
    guideline = input_guidelines(day) or ""
    base = (
        "Follow these rules (friendly, concrete, student-startup context).\n"
        "- Output exactly one JSON object inside a single ```json fenced block.\n"
        "- No pre/post text, markdown, emojis, comments, or repetition.\n"
        "- Header keys: version=\\\"AST-v1\\\", role=\\\"EEVE\\\", day.\n"
        "- Use Korean polite tone only inside JSON string values.\n"
        "- Do NOT score or mention delta/score. EEVE never scores.\n"
        "- Observe the following user input guideline:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "Schema: type=\\\"event_card\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- Domain: AI/LLM 제품 맥락의 구체 사건만 생성합니다(회의/토의 주제 금지).\n"
            "- Difficulty: 대학생 2~3명이 1주 내, <$200 클라우드 예산으로 다룰 수 있는 수준.\n"
            "- Category by day (guide, pick the mapped theme): day2=비용 급등, day3=지연/장애, day4=정확도/환각, day5=사용자 피드백 불만, day6=개인정보/거버넌스.\n"
            "- Summary must be 1-2 sentences and include: (a) 구체 컴포넌트/엔드포인트, (b) 수치화된 영향(다음 중 하나만 택해 제시: latency p95/avg, HTTP 500-rate, 정확도%, 환각률%, 요청당 비용, 처리량 rps), (c) 기간/환경, (d) 에러코드/로그 단서 1개.\n"
            "- eval_focus: [원인 정합성, 실행 가능성(즉시/단기/중기; 학생 팀 관점), 안전/측정(롤백·간이 모니터링·고객 공지)].\n"
            "- response_instructions: 해당 사건을 해결하기 위한 한 문단 계획을 요청합니다(간단한 도구/오픈소스/저예산 위주).\n"
            "- constraints: 반드시 '한 문단으로만 작성', '한국어 존댓말 사용'을 포함합니다.\n"
            "- Do not provide answers or analysis; only output the card JSON.\n"
        )
    return base + (
        "Schema: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- Write 1-2 sentences each. No lists/line breaks.\n"
        "- Student-startup lens: 과도한 엔터프라이즈 솔루션/예산 제안은 피하고, 간결한 이유와 요약을 제공합니다.\n"
        "- No scores, grades, or numeric deltas.\n"
    )


def _issuer_event_payload_strict(day: int) -> str:  # type: ignore[override]
    return (
        "Produce an event_card(JSON) for the given day.\n"
        f"- Day: {day}\n"
        "- AI/LLM 제품 맥락의 단일 사건을 제시하세요(회의/토의 금지). 대학생 팀이 1주 내 <$200 예산으로 처리 가능한 수준으로 작성하세요.\n"
        "- Summary에는 다음을 포함(1-2문장): 컴포넌트/엔드포인트, 수치화(하나만 선택: p95/avg 지연·500-rate·정확도%·환각률%·요청당 비용·rps), 기간/환경, 에러코드/로그 단서 1개.\n"
        "- eval_focus는 [원인 정합성, 실행 가능성(즉시/단기/중기; 학생 팀 관점), 안전/측정] 3개로 고정.\n"
        "- response_instructions에는 ‘한 문단 해결 계획(간단 도구/오픈소스/저예산)’ 요청을 포함.\n"
        "- constraints에는 '한 문단으로만 작성', '한국어 존댓말 사용'을 포함.\n"
        "- Required keys: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )


def _tester_system_prompt_strict(day: int) -> str:  # type: ignore[override]
    rubric = RUBRIC_BY_DAY.get(day, "")
    return (
        "Return exactly one JSON object (no extra text) in a ```json fenced block.\n"
        "Header: version=\\\"AST-v1\\\", role=\\\"OpenAI\\\", type=\\\"daily_score\\\", day.\n"
        "Keys: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "Scoring focus (student-startup, AI/LLM context): rate (1) 문제-해결 적합성/원인 정합성, (2) 실행 가능성(즉시/단기/중기; 1주·<$200·소수 인원 기준), (3) 안전/측정(간이 롤백·모니터링·고객 커뮤니케이션). 과도하게 모호/비현실/엔터프라이즈 의존(고가 SaaS·전문 인력 전제)은 감점.\n"
        f"{rubric}"
    )
