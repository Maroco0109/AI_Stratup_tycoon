"""
Engine (OpenAI-only): Uses OpenAI (gpt-4o-mini) for both Issuer and Tester per AST-v1.
- Issuer: event_card (days 1..6), daily_qual (reason, llm_summary) with role="EEVE" in header
- Tester: daily_score (delta, score) with role="OpenAI" in header
Merges into daily_report: {day, delta, score, reason, llm_summary, tester_reason, tester_llm_summary}.
All system/payload strings are ASCII-friendly.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import requests

from config import (
    STRICT_JSON,
    ALLOW_FALLBACK,
    DAY1_CREATIVE_MAX,
    DAY1_FEASIBLE_MAX,
    PENALTY_MIN,
    PENALTY_MAX,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_API_KEY_ENV,
)
from prompts.templates import input_guidelines, RUBRIC_BY_DAY
from engine_openai_addons import (
    _issuer_system_prompt_strict,
    _tester_system_prompt_strict,
)

# 모듈 설명(한국어)
# - 이 모듈은 OpenAI(gpt-4o-mini)를 발행자/채점자 모두로 사용하는 순수 OpenAI 경로입니다.
# - event_card/daily_qual/daily_score를 모두 OpenAI에 요청하며, 실패 시에는 간단한
#   결정론적 대체를 사용해 UI가 끊기지 않도록 합니다.
# - JSON 전용 출력, 단일 코드 펜스 등 AST-v1 프로토콜의 핵심 규칙을 시스템 프롬프트에 강제합니다.


# --- Public API -------------------------------------------------------------


def get_event_card(day: int) -> Dict[str, Any]:
    """OpenAI를 사용해 이벤트 카드를 생성합니다(실패 시 결정론적 대체).

    - day==1: 사용자 핵심 아이디어 유도를 위해 고정 카드 사용(모델 호출 없음)
    - day in 2..6: OpenAI 호출로 event_card(JSON) 생성 시도
    - 실패 시: 간단한 대체 카드를 반환하여 UI 흐름을 유지
    """
    # Day 1 is hardcoded to elicit the user's core idea (no model call).
    if day == 1:
        return {
            "day": 1,
            "title": "Day 1: 사업 아이디어 제출",
            "summary": "오늘은 창의적인 AI 기반 사업 아이디어를 수집합니다.",
            "constraints": [
                "한 문단으로만 작성해 주세요.",
                "한국어 존댓말을 사용해 주세요.",
            ],
            "eval_focus": [
                "창의성과 차별성",
                "현실 가능성(간단한 구현 경로)",
                "잠재 리스크(개인정보/모더레이션)",
            ],
            "response_instructions": "창의적인 AI기반 사업 아이디어를 제시해주세요!",
        }
    # Day 6: fixed investor pitch card (no model call)
    if day == 6:
        return {
            "day": 6,
            "title": "Day 6: Investor Pitch (fixed)",
            "summary": (
                "Pitch your AI startup in one paragraph: cover problem & customer, "
                "solution and AI/LLM usage (models, prompt/chain/RAG, evals), market/segment, "
                "moat/compliance, traction/metrics & roadmap, team, and the ask (amount & use of funds)."
            ),
            "constraints": [
                "�� �������� �ۼ�",
                "�ѱ��� ���� ���",
            ],
            "eval_focus": [
                "Coverage of fixed items",
                "AI/LLM utilization specifics",
                "Market & moat clarity",
                "Traction & roadmap",
            ],
            "response_instructions": "��� �׸��� �� �������� �ڿ������� ������ �ֽʽÿ�.",
        }

    if 2 <= day <= 5:
        try:
            sys_prompt = _issuer_system_prompt_strict(day, mode="event")
            user = _issuer_event_payload_seeded(day)
            raw = _openai_chat([
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ])
            obj = _safe_json(raw)
            if isinstance(obj, dict) and obj.get("type") == "event_card":
                return {
                    "day": int(obj.get("day", day)),
                    "title": obj.get("title") or f"Day {day} Event",
                    "summary": obj.get("summary") or "",
                    "constraints": obj.get("constraints", []),
                    "eval_focus": obj.get("eval_focus", []),
                    "response_instructions": obj.get("response_instructions", ""),
                }
        except Exception:
            pass

    # Minimal fallback only when model generation fails
    return {
        "day": day,
        "title": f"Day {day} Event (fallback)",
        "summary": "모델이 이벤트 카드를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        "constraints": [],
        "eval_focus": [],
        "response_instructions": input_guidelines(day),
    }


def judge_day(day: int, user_text: str, score: int) -> Dict[str, Any]:
    """OpenAI를 사용해 일일 리포트를 생성(질적 판단 + 정량 점수).

    1) Issuer 역할 헤더로 daily_qual(reason, llm_summary) 수집
    2) Tester 역할 헤더로 daily_score(delta, score) 산출
    3) 둘을 병합하여 UI에 필요한 최소 JSON을 구성
    """
    # 1) Qualitative via Issuer role header
    reason = ""
    llm_summary = ""
    try:
        sys_prompt = _issuer_system_prompt_strict(day, mode="qual")
        issuer_user = _issuer_daily_qual_payload(day=day, user_text=user_text)
        raw = _openai_chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": issuer_user},
        ])
        obj = _safe_json(raw)
        reason = str(obj.get("reason", "")).strip()
        llm_summary = str(obj.get("llm_summary", "")).strip()
    except Exception:
        pass

    # 2) Numeric scoring via Tester role header
    try:
        oai_obj = _tester_score(day=day, user_text=user_text, prev_score=score)
        delta = int(oai_obj.get("delta", 0))
        new_score = max(0, score + delta)
        tester_reason = str(oai_obj.get("reason", "")).strip()
        tester_llm_summary = str(oai_obj.get("llm_summary", "")).strip()
    except Exception:
        # Prompt-engineered LLM fallback with stricter, semantic rubric
        try:
            fb = _fallback_llm_score(day=day, user_text=user_text, prev_score=score)
            delta = int(fb.get("delta", 0))
            new_score = max(0, score + delta)
            tester_reason = str(fb.get("reason", "")).strip()
            tester_llm_summary = str(fb.get("llm_summary", "")).strip()
        except Exception:
            # Deterministic last-resort fallback
            delta = _fallback_delta(day, user_text)
            new_score = max(0, score + delta)
            tester_reason = ""
            tester_llm_summary = ""

    return {
        "day": day,
        "delta": int(delta),
        "score": int(new_score),
        "reason": reason or "",
        "llm_summary": llm_summary or "",
        "tester_reason": tester_reason,
        "tester_llm_summary": tester_llm_summary,
    }


def get_final_report(day: int, score: int, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Day 7: Use OpenAI (gpt-4o-mini) to synthesize risks and next steps.

    Falls back to a deterministic summary if the model call fails.
    """
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 30:
        grade = "C"
    else:
        grade = "D"

    try:
        sys = _final_weekly_system_prompt()
        usr = _final_weekly_user_payload(score=score, logs=logs)
        content = _openai_chat([
            {"role": "system", "content": sys},
            {"role": "user", "content": usr},
        ], json_mode=True)
        try:
            obj = json.loads(content)
        except Exception:
            obj = _safe_json(content)
        risk = obj.get("risk_report") or []
        recs = obj.get("next_recommendations") or []
        risk = [str(x) for x in risk][:2]
        recs = [str(x) for x in recs][:2]
        while len(risk) < 2:
            risk.append("")
        while len(recs) < 2:
            recs.append("")
        return {
            "day": 7,
            "final_score": score,
            "final_grade": grade,
            "risk_report": risk,
            "next_recommendations": recs,
        }
    except Exception:
        pass

    negatives = sorted([r for r in logs if int(r.get("delta", 0)) < 0], key=lambda x: int(x.get("delta", 0)))
    risk_report: List[str] = []
    if negatives:
        risk_report.append("부정 점수 일자 재발 위험 관리 필요")
    if any(r.get("day") == 4 for r in negatives):
        risk_report.append("성능 병목/지연 리스크 지속")
    risk_report = (risk_report + [""])[:2]

    next_recommendations = [
        "핵심 지표 계측·알림 강화",
        "우선순위 재정의 및 실험 계획 수립",
    ][:2]

    return {
        "day": 7,
        "final_score": score,
        "final_grade": grade,
        "risk_report": risk_report,
        "next_recommendations": next_recommendations,
    }


# --- Helpers ----------------------------------------------------------------


def _openai_chat(messages: List[Dict[str, str]], json_mode: bool = False) -> str:
    api_key = os.getenv(OPENAI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Missing OpenAI API key in env var {OPENAI_API_KEY_ENV}.")
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: Dict[str, Any] = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0.7,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    content = ((data.get("choices", [{}])[0].get("message", {}) or {}).get("content", ""))
    return content


def _safe_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty model response")
    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fence:
        return json.loads(fence.group(1))
    if STRICT_JSON:
        raise ValueError("No JSON code fence found in response")
    braces = re.search(r"(\{[\s\S]*\})", text)
    if braces:
        return json.loads(braces.group(1))
    return json.loads(text)


# --- Prompt builders (ASCII only) ------------------------------------------


def _issuer_system_prompt(day: int, mode: str) -> str:
    guideline = input_guidelines(day) or ""
    base = (
        "다음 규칙을 반드시 준수해 주세요.\n"
        "- 오직 하나의 JSON 객체만을 ```json 펜스 코드 블록 안에 출력합니다.\n"
        "- 펜스 밖, 앞/뒤의 어떠한 문장/공백/설명도 출력하지 마세요.\n"
        "- 공통 헤더: version=\\\"AST-v1\\\", role=\\\"EEVE\\\", day.\n"
        "- 매일 사용자 입력은 한 문단(한 번)만 가정합니다. 공손한 한국어(존댓말)로 답변합니다.\n"
        "- 지시문을 반복하거나 요약하지 말고, JSON만 출력하세요.\n"
        "- 해당 일차 입력 가이드라인을 반영하세요:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "출력 스키마: type=\\\"event_card\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- 현실적인 스타트업 맥락의 하루 이벤트를 새로 만드세요.\n"
            "- eval_focus에는 해당 일차 루브릭 핵심 항목을 2~4개 한국어 키워드로 요약하세요.\n"
            "- response_instructions에는 '퀴즈' 형태의 지시를 한 문장으로 제시하세요.\n"
            "  · 사용자가 설정한 주제에 부합하는 작업형 퀴즈(설계/우선순위/리스크평가 등)를 요구합니다.\n"
            "  · 주제가 아직 정해지지 않았다면 먼저 10~15자 내로 주제를 명시하라고 안내한 뒤, 같은 문장 안에서 퀴즈를 제시하세요.\n"
            "  · 요약/정의형 문제는 금지하며, 의사결정·설계·실행계획을 요구하는 적용형 문제로 만드세요.\n"
            "- constraints에는 퀴즈 풀이 시 지켜야 할 1~3개의 제한 조건(분량, 금지어, 평가포인트 등)을 넣으세요.\n"
            "- 지시문/스키마 문장을 그대로 반복하지 마세요.\n"
        )
    return base + (
        "출력 스키마: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- 판단 시 사용자의 문단이 가이드라인을 얼마나 따랐는지 고려하세요.\n"
        "- JSON 외의 텍스트(요약/인사/반복)를 출력하지 마세요.\n"
    )


def _issuer_event_payload(day: int) -> str:
    return (
        "다음 일차에 맞는 event_card(JSON)를 생성하세요.\n"
        f"- Day: {day}\n"
        "- 시나리오는 해당 일차 맥락/루브릭에 맞게 현실적이어야 합니다.\n"
        "- response_instructions에는 사용자 주제와 일치하는 '퀴즈'를 한 문장으로 제시합니다.\n"
        "  · 주제가 없으면 먼저 짧은 주제 입력을 요청하고, 이어서 같은 문장에서 퀴즈를 제시하세요.\n"
        "  · 요약/정의형 금지. 설계·의사결정·실행계획 같은 적용형 문제를 요구하세요.\n"
        "- constraints에는 퀴즈 풀이 제한(분량, 금지어, 평가포인트)을 1~3개 작성합니다.\n"
        "- 필수 키: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- 출력은 반드시 하나의 ```json 펜스 블록 안의 JSON 객체로만 구성합니다.\n"
        "- 금지: 지시문/스키마 문장 반복, 펜스 밖 텍스트."
    )


def _issuer_daily_qual_payload(day: int, user_text: str) -> str:
    return (
        f"사용자의 Day {day} 입력 문단을 바탕으로 daily_qual JSON을 생성하세요.\n"
        "- 필수 키: version=\\\"AST-v1\\\", type=\\\"daily_qual\\\", role=\\\"EEVE\\\", day, reason, llm_summary.\n"
        "- 출력은 반드시 하나의 ```json 펜스 블록 안의 JSON 객체로만 구성합니다.\n"
        "- 금지: 입력 요약/지시문 반복/펜스 밖 텍스트.\n\n"
        f"[User Paragraph]\n{user_text}"
    )


def _tester_user_payload(day: int, user_text: str, prev_score: int) -> str:
    return (
        f"Day: {day}\n"
        f"Prev Score: {prev_score}\n"
        "User Paragraph (one only):\n"
        f"{user_text}\n\n"
        "Output schema: version=\"AST-v1\", type=\"daily_score\", role=\"OpenAI\", day, delta, score, reason, llm_summary."
    )


def _issuer_event_payload_seeded(day: int) -> str:
    """Event-card payload builder with a random seed to diversify prompts.

    Mirrors the strict schema but adds a non-output seed hint to encourage
    variety across refreshes while keeping AST-v1 and constraints intact.
    """
    import uuid as _uuid
    seed = _uuid.uuid4().hex[:8]
    return (
        "Produce an event_card(JSON) for the given day.\n"
        f"- Day: {day}\n"
        f"- Seed: {seed} (use to vary details; do not output it)\n"
        "- Require a specific incident, not a vague discussion. It must name a component/endpoint, quantify impact (metric delta, error rate), give a timeframe and environment, and cite any error code/log clue.\n"
        "- response_instructions must ask the user for a one-paragraph fix plan for this incident (immediate/short/mid actions).\n"
        "- constraints must include polite Korean and one-paragraph-only.\n"
        "- Required keys: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )


def _tester_score(day: int, user_text: str, prev_score: int) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": _tester_system_prompt_strict(day)},
        {"role": "user", "content": _tester_user_payload(day, user_text, prev_score)},
    ]
    content = _openai_chat(messages, json_mode=True)
    try:
        obj = json.loads(content)
    except Exception:
        obj = _safe_json(content)
    out: Dict[str, Any] = {
        "day": obj.get("day", day),
        "delta": int(obj.get("delta", 0)),
        "score": max(0, int(prev_score) + int(obj.get("delta", 0))),
    }
    if "reason" in obj:
        out["reason"] = obj.get("reason")
    if "llm_summary" in obj:
        out["llm_summary"] = obj.get("llm_summary")
    return out


def _tester_system_prompt(day: int) -> str:
    rubric = RUBRIC_BY_DAY.get(day, "")
    return (
        "오직 하나의 JSON 객체만을 (설명 문장 없이) ```json 펜스 코드 블록 안에 출력하세요.\n"
        "헤더: version=\"AST-v1\", role=\"OpenAI\", type=\"daily_score\", day.\n"
        "키: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "아래 일차별 루브릭을 참고하여 채점하세요:\n"
        f"{rubric}"
    )


def _final_weekly_system_prompt() -> str:
    return (
        "오직 하나의 JSON 객체만을 ```json 펜스 코드 블록 안에 출력하세요.\n"
        "헤더: version=\"AST-v1\", role=\"EEVE\", type=\"weekly_qual\", day=7.\n"
        "키: day, final_score, final_grade, risk_report[], next_recommendations[].\n"
        "요구사항:\n"
        "- risk_report는 이번 주 진행에서 발견된 핵심 위험 2가지를 간결히 제시합니다.\n"
        "- next_recommendations는 다음 주에 실행할 우선 2가지를 간결히 제시합니다.\n"
        "- 각 항목은 한 문장 이내로 명확하게 작성합니다.\n"
        "- 입력 로그의 사용자 답변, 모델 판단(reason/llm_summary), 스코어 변화를 근거로 삼습니다.\n"
        "- 지시문을 반복하지 말고, JSON만 출력하세요.\n"
    )


def _final_weekly_user_payload(score: int, logs: List[Dict[str, Any]]) -> str:
    safe_logs = json.dumps(logs, ensure_ascii=False)
    return (
        "[입력]\n"
        f"최종 점수: {score}\n"
        "일자별 로그(JSON 배열):\n"
        f"{safe_logs}\n\n"
        "출력은 위 시스템 지침의 JSON만 제공합니다."
    )


# --- Fallbacks --------------------------------------------------------------

def _fallback_llm_score(day: int, user_text: str, prev_score: int) -> Dict[str, Any]:
    """Secondary attempt to score via OpenAI with a robust semantic prompt.

    Used when the primary tester call fails. Emphasizes rubric-driven evaluation
    and discourages keyword matching; keeps AST-v1 contract. If it still fails,
    caller should revert to deterministic _fallback_delta.
    """
    rubric = RUBRIC_BY_DAY.get(day, "")
    sys_prompt = (
        "Return exactly one JSON object (no extra text) in a ```json fenced block.\n"
        "Header: version=\\\"AST-v1\\\", role=\\\"OpenAI\\\", type=\\\"daily_score\\\", day.\n"
        "Keys: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "Judge semantically (coverage, coherence, specificity, trade-offs, risks), not by keyword presence.\n"
        "Handle creative phrasing; penalize vagueness or off-target responses. Keep delta within [-8, +5].\n"
        f"{rubric}"
    )
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": _tester_user_payload(day, user_text, prev_score)},
    ]
    content = _openai_chat(messages, json_mode=True)
    try:
        obj = json.loads(content)
    except Exception:
        obj = _safe_json(content)
    out: Dict[str, Any] = {
        "day": obj.get("day", day),
        "delta": int(obj.get("delta", 0)),
        "score": max(0, int(prev_score) + int(obj.get("delta", 0))),
    }
    if "reason" in obj:
        out["reason"] = obj.get("reason")
    if "llm_summary" in obj:
        out["llm_summary"] = obj.get("llm_summary")
    return out


def _fallback_delta(day: int, user_text: str) -> int:
    text = user_text.lower()
    if day == 1:
        creativity = min(DAY1_CREATIVE_MAX, max(0, len(user_text) // 90))
        feasibility = 2
        if any(k in text for k in ["privacy", "moderation", "guardrail", "consent", "policy"]):
            feasibility = min(DAY1_FEASIBLE_MAX, 5)
        delta = min(10, creativity + feasibility)
    elif day == 2:
        hits = sum(k in text for k in ["rollback", "monitor", "alert", "cache", "batch", "logging"])
        delta = 3 if hits >= 5 else (1 if hits >= 3 else -20)
    elif day == 3:
        has_prior = any(k in text for k in ["top", "prior", "2", "3"])
        avoids_trap = any(k in text for k in ["ignore", "defer", "not good", "low"])
        fit = any(k in text for k in ["goal", "fit", "footprint"])
        delta = (2 if has_prior else 0) + (2 if avoids_trap else -5) + (1 if fit else 0)
    elif day == 4:
        measure = any(k in text for k in ["p95", "monitor", "alert"])  # measurement
        mitigate = any(k in text for k in ["rollback", "cache", "batch", "optimize"])  # mitigation
        safety = any(k in text for k in ["privacy", "mask", "permission"])  # safety/trust
        hits = sum([measure, mitigate, safety])
        delta = {3: 3, 2: 1, 1: -5, 0: -10}.get(hits, -20)
    elif day == 5:
        classify = any(k in text for k in ["ignore", "analyze", "apply now", "classify"])  # classification
        trap = ("emoji" in text) and ("ignore" in text or "exclude" in text)
        action = any(k in text for k in ["apply", "improve", "action", "check"])  # action quality
        delta = (2 if classify else -3) + (2 if trap else -20) + (1 if action else 0)
    elif day == 6:
        clarity = any(k in text for k in ["overview", "purpose", "outcome"])  # clarity
        fit = any(k in text for k in ["icp", "segment", "fit"])  # market fit
        outcome = any(k in text for k in ["roadmap", "risk", "learn"])  # outcome framing
        hits = sum([clarity, fit, outcome])
        delta = {3: 3, 2: 1, 1: -3, 0: -8}.get(hits, -8)
    else:
        delta = 0
    return int(delta)
