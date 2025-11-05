"""
Engine: Orchestrates EEVE (Issuer) and OpenAI (Tester) per AST-v1.
- EEVE: event_card (days 1..6), daily_qual (reason, llm_summary)
- OpenAI: daily_score (delta, score) — now also returns reason, llm_summary
We merge into daily_report: {day, delta, score, reason, llm_summary, tester_reason, tester_llm_summary}.
All system/payload strings are ASCII to avoid encoding issues.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List

import requests

from config import (
    OLLAMA_BASE_URL,
    MODEL_NAME,
    TEMPERATURE,
    NUM_CTX,
    STRICT_JSON,
    ALLOW_FALLBACK,
    DAY1_CREATIVE_MAX,
    DAY1_FEASIBLE_MAX,
    PENALTY_MIN,
    PENALTY_MAX,
)
from prompts.templates import input_guidelines, RUBRIC_BY_DAY


# --- Public API -------------------------------------------------------------

def get_event_card(day: int) -> Dict[str, Any]:
    """이벤트 카드 조회

    설명
    - 가능하면 EEVE(로컬 Ollama)를 호출하여 event_card(JSON)를 생성합니다.
    - 실패 시 결정론적(fallback) 카드로 대체하여 UI 흐름이 끊기지 않도록 합니다.

    매개변수
    - day: 요청 일차(1~6일차만 카드 생성; 1일차는 고정 카드)

    반환
    - 카드 딕셔너리: {day, title, summary, constraints[], eval_focus[], response_instructions}
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
    if 2 <= day <= 5:
        try:
            eeve_sys = _eeve_system_prompt_relaxed(day, mode="event")
            user = _eeve_event_payload_relaxed(day)
            raw = _ollama_chat([
                {"role": "system", "content": eeve_sys},
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

    # Day 6 deterministic investor pitch card if generation failed above
    if day == 6:
        return {
            "day": 6,
            "title": "Day 6: 투자자 피칭",
            "summary": (
                "당신의 AI 스타트업을 한 문단으로 피칭하세요: 문제점과 고객, "
                "솔루션 및 AI/LLM 활용 방법(모델, 프롬프트/체인/RAG, 평가), 시장/세그먼트, "
                "경쟁 우위/컴플라이언스, 트랙션/지표 및 로드맵, 팀, 그리고 투자 요청(금액과 자금 사용 계획)을 포함해 주세요."
            ),
            "constraints": [
                "한 문단으로 작성",
                "한국어 존댓말 사용",
            ],
            "eval_focus": [
                "필수 항목 포괄성",
                "AI/LLM 활용 구체성",
                "시장 및 경쟁 우위 명확성",
                "트랙션 및 로드맵",
            ],
            "response_instructions": "모든 항목을 한 문단으로 자연스럽게 포함해 주십시오.",
        }

    # 모델이 받아오도록 수정해야함
    # 한글로 주도록 수정해야함
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
    """일일 리포트 생성(질적 판단 + 정량 점수 병합)

    흐름
    1) EEVE: daily_qual(JSON) — reason, llm_summary만 수집(점수 금지)
    2) OpenAI: daily_score(JSON) — delta, score(및 선택적 reason/llm_summary)
    3) 둘을 병합하여 UI에 표시할 일일 리포트를 구성합니다.

    매개변수
    - day: 현재 일차(1~6)
    - user_text: 사용자의 하루 한 문단 답변
    - score: 기존 누적 점수(prev_score)

    반환
    - 병합 리포트 딕셔너리
    """
    # 1) EEVE qualitative
    reason = ""
    llm_summary = ""
    try:
        eeve_sys = _eeve_system_prompt_relaxed(day, mode="qual")
        eeve_user = _eeve_daily_qual_payload_clean(day=day, user_text=user_text)
        eeve_raw = _ollama_chat([
            {"role": "system", "content": eeve_sys},
            {"role": "user", "content": eeve_user},
        ])
        eeve_obj = _safe_json(eeve_raw)
        reason = str(eeve_obj.get("reason", "")).strip()
        llm_summary = str(eeve_obj.get("llm_summary", "")).strip()
    except Exception:
        pass

    # 2) OpenAI numeric scoring (+ tester qualitative when present)
    try:
        oai_obj = _openai_score(day=day, user_text=user_text, prev_score=score)
        delta = int(oai_obj.get("delta", 0))
        new_score = max(0, score + delta)
        tester_reason = str(oai_obj.get("reason", "")).strip()
        tester_llm_summary = str(oai_obj.get("llm_summary", "")).strip()
    except Exception:
        # Prompt-engineered LLM fallback first (semantic, rubric-based; avoids keyword hits)
        try:
            fb = _fallback_llm_score(day=day, user_text=user_text, prev_score=score)
            delta = int(fb.get("delta", 0))
            new_score = max(0, score + delta)
            tester_reason = str(fb.get("reason", "")).strip()
            tester_llm_summary = str(fb.get("llm_summary", "")).strip()
        except Exception:
            # Deterministic last-resort fallback (kept for robustness)
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
    """Day 7: Use EEVE to synthesize risks and next steps from logs.

    Falls back to a deterministic summary if the model call fails.
    """
    # Deterministic grade (kept for consistency)
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 30:
        grade = "C"
    else:
        grade = "D"

    # Try model-based weekly synthesis
    try:
        sys = _final_weekly_system_prompt()
        usr = _final_weekly_user_payload(score=score, logs=logs)
        raw = _ollama_chat([
            {"role": "system", "content": sys},
            {"role": "user", "content": usr},
        ])
        obj = _safe_json(raw)
        risk = obj.get("risk_report") or []
        recs = obj.get("next_recommendations") or []
        # Normalize lengths to exactly 2
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

    # Fallback: derive two concise items from logs
    negatives = sorted([r for r in logs if int(r.get("delta", 0)) < 0], key=lambda x: int(x.get("delta", 0)))
    risk_report: List[str] = []
    if negatives:
        risk_report.append("부정 점수 일자 재발 위험 관리 필요")
    if any(r.get("day") == 4 for r in negatives):
        risk_report.append("성능 병목/지연 리스크 지속")
    # Ensure exactly 2
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

def _ollama_chat(messages: List[Dict[str, str]]) -> str:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX},
    }
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and "message" in data:
        return data["message"].get("content", "")
    if isinstance(data, list):
        return "".join(chunk.get("message", {}).get("content", "") for chunk in data)
    return ""


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


def _openai_chat_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """OpenAI 대신 EEVE(Ollama)를 통해 테스트용 JSON을 생성합니다.

    - 함수명/호출 계약은 유지하지만, 내부적으로 로컬 EEVE 모델을 사용해
      채점 JSON을 생성함으로써 호출 경로를 단일화합니다.
    """
    raw = _ollama_chat(messages)
    return _safe_json(raw)


# --- Prompt builders (ASCII only) ------------------------------------------

def _eeve_system_prompt_clean(day: int, mode: str) -> str:
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
            "- response_instructions에는 위 가이드라인을 한 문장으로 간결히 반영하세요.\n"
            "- 지시문/스키마 문장을 그대로 반복하지 마세요.\n"
        )
    return base + (
        "출력 스키마: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- 판단 시 사용자의 문단이 가이드라인을 얼마나 따랐는지 고려하세요.\n"
        "- JSON 외의 텍스트(요약/인사/반복)를 출력하지 마세요.\n"
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


def _openai_system_prompt(day: int) -> str:
    if day == 6:
        rubric = (
            "[Day 6 Rubric — Investor Pitch (fixed questions)]\n"
            "- Coverage & Clarity (0..+3): problem/customer, solution overview, team, and ask (amount/use of funds) in one paragraph.\n"
            "- AI/LLM Utilization (0..+2): chosen models, prompting/chain/RAG, offline evals/guardrails.\n"
            "- Market & Moat (0..+2): market size/segment and durable moat (incl. privacy/compliance).\n"
            "- Traction & Roadmap (0..+1): current metrics/pilots and near-term plan.\n"
            "- Clamp delta in [-8, +5]; penalize omissions/overclaims, reward solid coverage."
        )
    else:
        rubric = RUBRIC_BY_DAY.get(day, "")
    return (
        "오직 하나의 JSON 객체만을 (설명 문장 없이) ```json 펜스 코드 블록 안에 출력하세요.\n"
        "헤더: version=\"AST-v1\", role=\"OpenAI\", type=\"daily_score\", day.\n"
        "키: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "아래 일차별 루브릭을 참고하여 채점하세요:\n"
        f"{rubric}"
    )


def _eeve_event_payload_clean(day: int) -> str:
    return (
        "다음 일차에 맞는 event_card JSON을 생성하세요.\n"
        f"- Day: {day}\n"
        "- 시나리오는 해당 일차의 맥락과 루브릭에 맞게 현실적으로 만듭니다.\n"
        "- 필수 키: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- 출력은 반드시 하나의 ```json 펜스 블록 안의 JSON 객체로만 구성합니다.\n"
        "- 금지: 지시문/스키마 문장 반복, 펜스 밖 텍스트."
    )


def _eeve_event_payload_diverse(day: int) -> str:
    """Variant of the event payload that injects a day-based theme and a random seed
    so repeated calls generate varied, day-appropriate incidents.

    Kept separate to avoid breaking callers that still rely on the original helper.
    """
    _themes = {
        2: "Cost spike in LLM usage (token/latency/caching)",
        3: "Reliability incident (latency/outage, dependency failure)",
        4: "Model quality drift or safety/compliance risk",
        5: "User feedback/UX complaint impacting adoption",
        6: "Investor pitch preparation (coverage-focused)",
    }
    theme = _themes.get(day, "General AI/LLM incident")
    seed = uuid.uuid4().hex[:8]
    return (
        "Produce an event_card(JSON) for the given day.\n"
        f"- Day: {day}\n"
        f"- Theme: {theme}\n"
        f"- Seed: {seed} (use to vary details; do not output it)\n"
        "- Make it a specific incident: name component/endpoint, quantify impact (metric delta or error rate), timeframe/env, and one error code/log clue.\n"
        "- Required keys: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )


def _eeve_daily_qual_payload_clean(day: int, user_text: str) -> str:
    return (
        f"사용자의 Day {day} 입력 문단을 바탕으로 daily_qual JSON을 생성하세요.\n"
        "- 필수 키: version=\\\"AST-v1\\\", type=\\\"daily_qual\\\", role=\\\"EEVE\\\", day, reason, llm_summary.\n"
        "- 출력은 반드시 하나의 ```json 펜스 블록 안의 JSON 객체로만 구성합니다.\n"
        "- 금지: 입력 요약/지시문 반복/펜스 밖 텍스트.\n\n"
        f"[User Paragraph]\n{user_text}"
    )


def _scoring_user_payload(day: int, user_text: str, prev_score: int) -> str:
    return (
        f"Day: {day}\n"
        f"Prev Score: {prev_score}\n"
        "User Paragraph (one only):\n"
        f"{user_text}\n\n"
        "Output schema: version=\"AST-v1\", type=\"daily_score\", role=\"OpenAI\", day, delta, score, reason, llm_summary."
    )


def _openai_score(day: int, user_text: str, prev_score: int) -> Dict[str, Any]:
    """OpenAI(또는 EEVE를 통한 스코어러 대행) 호출로 정량 점수를 산출합니다.

    - messages: 시스템 프롬프트(룰/루브릭) + 사용자 페이로드(이전 점수/답변)
    - 응답: daily_score(JSON) — {day, delta, score, (선택)reason, (선택)llm_summary}
    - score는 엔진에서도 안전하게 재계산하여 0 미만으로 내려가지 않도록 보정합니다.
    """
    messages = [
        {"role": "system", "content": _openai_system_prompt(day)},
        {"role": "user", "content": _scoring_user_payload(day, user_text, prev_score)},
    ]
    obj = _openai_chat_json(messages)
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


# --- Fallbacks --------------------------------------------------------------

def _fallback_llm_score(day: int, user_text: str, prev_score: int) -> Dict[str, Any]:
    """LLM-based fallback scoring using the local EEVE model (via Ollama).

    - Keeps AST-v1 JSON contract but emphasizes semantic, rubric-based evaluation.
    - Avoids keyword-hit heuristics; clamps delta implicitly via rubric instructions.
    - If anything fails, caller should revert to deterministic _fallback_delta.
    """
    rubric = RUBRIC_BY_DAY.get(day, "")
    sys = (
        "Return exactly one JSON object (no extra text) inside one ```json fenced block.\n"
        "Header: version=\\\"AST-v1\\\", role=\\\"OpenAI\\\", type=\\\"daily_score\\\", day.\n"
        "Keys: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "Judge semantically, not by keywords: assess coverage, coherence, specificity, trade-offs, and risks.\n"
        "Handle creative phrasing; do not require exact phrases. Penalize vagueness or off-target plans.\n"
        "Delta bounds: prefer small positives for solid plans; negatives for vague/misaligned; keep within [-8, +5].\n"
        f"{rubric}"
    )
    usr = (
        f"Day: {day}\n"
        f"Prev Score: {prev_score}\n"
        "User Paragraph (one only):\n"
        f"{user_text}\n\n"
        "Output schema: version=\\\"AST-v1\\\", type=\\\"daily_score\\\", role=\\\"OpenAI\\\", day, delta, score, reason, llm_summary."
    )
    raw = _ollama_chat([
        {"role": "system", "content": sys},
        {"role": "user", "content": usr},
    ])
    obj = _safe_json(raw)
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
    """OpenAI가 사용 불가할 때 사용하는 결정론적 점수 증감(delta) 계산기.

    - 단순 키워드 존재 여부와 조합으로 휴리스틱한 가/감점을 적용합니다.
    - 각 일차별로 핵심 요소를 최소화하여 점수 흐름의 일관성을 보장합니다.
    """
    text = user_text.lower()
    if day == 1:
        creativity = min(DAY1_CREATIVE_MAX, max(0, len(user_text) // 90))
        feasibility = 2
        if any(k in text for k in ["privacy", "moderation", "guardrail", "consent", "policy"]):
            feasibility = min(DAY1_FEASIBLE_MAX, 5)
        delta = min(10, creativity + feasibility)
    elif day == 2:
        hits = sum(k in text for k in ["rollback", "monitor", "alert", "cache", "batch", "logging"])
        delta = 3 if hits >= 5 else (1 if hits >= 3 else -10)
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
        delta = {3: 3, 2: 1, 1: -5, 0: -10}.get(hits, -10)
    elif day == 5:
        classify = any(k in text for k in ["ignore", "analyze", "apply now", "classify"])  # classification
        trap = ("emoji" in text) and ("ignore" in text or "exclude" in text)
        action = any(k in text for k in ["apply", "improve", "action", "check"])  # action quality
        delta = (2 if classify else -3) + (2 if trap else -10) + (1 if action else 0)
    elif day == 6:
        # Investor pitch coverage heuristic
        g_problem = any(k in text for k in ["problem", "customer", "pain"])  # problem & customer
        g_solution_ai = any(k in text for k in ["ai", "llm", "model", "rag", "prompt", "eval"])  # AI/LLM specifics
        g_market_moat = any(k in text for k in ["market", "segment", "moat", "privacy", "compliance", "safety"])  # market & moat
        g_traction = any(k in text for k in ["traction", "metric", "kpi", "pilot", "mrr", "users", "roadmap"])  # traction & roadmap
        g_team_ask = any(k in text for k in ["team", "ask", "fund", "funding", "use of funds", "budget"])  # team & ask
        coverage = sum([g_problem, g_solution_ai, g_market_moat, g_traction, g_team_ask])
        delta = {5: 5, 4: 3, 3: 1, 2: -3, 1: -5, 0: -8}.get(coverage, -8)
    else:
        delta = 0
    return int(delta)


# --- Relaxed prompt builders (additive, used by call sites) ---------------

def _eeve_system_prompt_relaxed(day: int, mode: str) -> str:
    """A lighter system prompt that preserves AST-v1 and JSON-fence rules
    while giving the model freedom in event style and content.
    """
    guideline = input_guidelines(day) or ""
    base = (
        "아래 최소 규칙만 지켜 주세요.\n"
        "- 단 하나의 JSON 객체를 하나의 ```json 펜스 블록 안에만 출력합니다.\n"
        "- 펜스 밖 텍스트/이모지/주석/반복은 금지합니다.\n"
        "- 헤더 키: version=\\\"AST-v1\\\", role=\\\"EEVE\\\", day.\n"
        "- 한국어 존댓말을 사용합니다. EEVE는 점수/delta를 계산하지 않습니다.\n"
        "- (선택) 영감용 가이드라인:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "스키마: type=\\\"event_card\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- 사건/상황/기회 등 어떤 형식이든 자유롭게 제시해도 됩니다(현실적이면 충분).\n"
            "- summary는 1~2문장 권장(수치·메트릭은 선택).\n"
            "- eval_focus는 1~3개 짧은 초점(형식 자유).\n"
            "- response_instructions는 한 문장으로 한 문단 답변을 부드럽게 요청하세요.\n"
            "- 해설/정답은 쓰지 말고 카드 JSON만 출력하세요.\n"
        )
    return base + (
        "스키마: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- 각 항목은 1~2문장 자연스러운 문장으로 작성합니다(목록/줄바꿈 금지).\n"
        "- 점수/수치 언급은 금지합니다.\n"
    )


def _eeve_event_payload_relaxed(day: int) -> str:
    """Minimal user payload to elicit a freer event card while keeping schema."""
    return (
        "다음 조건으로 event_card(JSON)를 출력해 주세요.\n"
        f"- Day: {day}\n"
        "- 스타트업 맥락에서 현실적이되, 사건/상황/기회를 창의적으로 제시해도 됩니다(수치 선택).\n"
        "- 필수 키: version=\\\"AST-v1\\\", type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- 반드시 하나의 ```json 펜스 안에 단일 JSON 객체만 출력하세요."
    )
