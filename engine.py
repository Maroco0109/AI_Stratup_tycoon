"""
Game orchestrator aligned with README and prompts/rulebook.md.

Model usage plan
- EEVE (Issuer):
  * Issues daily event cards (type=event_card) instructing the user to reply
    with a single paragraph in Korean polite tone.
  * After the user replies, produces qualitative fields only (type=daily_qual):
    reason, llm_summary. Never returns numeric scores.
- OpenAI (Tester):
  * Scores the user's one-paragraph reply and returns delta and score only
    (type=daily_score). Uses the scoring table in the rulebook.

We merge both outputs into a daily_report: {day, delta, score, reason, llm_summary}.

Implementation notes
- EEVE via Ollama: POST {OLLAMA_BASE_URL}/chat with messages [{role, content}, ...]
- OpenAI via Chat Completions: POST {OPENAI_BASE_URL}/chat/completions with
  response_format=json_object
- Rulebook parsing: extract the specific SYSTEM sections for EEVE and OpenAI
  from prompts/rulebook.md so each model receives its tailored instructions.
- Robust JSON extraction via _safe_json for EEVE; OpenAI uses JSON response_format.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List
from pathlib import Path

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
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_API_KEY_ENV,
)
# No direct template imports; engine extracts SYSTEM prompts from rulebook.md


def get_event_card(day: int) -> Dict[str, Any]:
    """Return an event card for the given day via EEVE when possible.

    - Preferred (days 1..6): Ask EEVE (Issuer) to produce a type=event_card JSON.
    - Fallback: deterministic local event card when model call fails or for day 7.
    """
    if 1 <= day <= 6:
        try:
            eeve_sys = _eeve_system_prompt()
            user = _eeve_event_payload(day)
            raw = _ollama_chat([
                {"role": "system", "content": eeve_sys},
                {"role": "user", "content": user},
            ])
            obj = _safe_json(raw)
            if isinstance(obj, dict) and obj.get("type") == "event_card":
                return {
                    "day": int(obj.get("day", day)),
                    "title": obj.get("title") or "Event",
                    "summary": obj.get("summary") or "",
                    "constraints": obj.get("constraints", []),
                    "eval_focus": obj.get("eval_focus", []),
                    "response_instructions": obj.get("response_instructions", ""),
                }
        except Exception:
            pass

    base = {
        1: {"day": 1, "title": "Idea Polishing", "summary": "Refine your AI startup idea: value prop, target users, and edge."},
        2: {"day": 2, "title": "Obstacle: Cost Overruns", "summary": "Cloud inference costs spike. Propose immediate mitigations and a plan."},
        3: {"day": 3, "title": "User Feedback", "summary": "Early testers are confused by onboarding. Clarify flows and messaging."},
        4: {"day": 4, "title": "Performance Bottleneck", "summary": "Latency exceeds SLA. Describe profiling steps and prioritization."},
        5: {"day": 5, "title": "Investor Meeting", "summary": "Craft a compelling pitch and metrics narrative for seed VCs."},
        6: {"day": 6, "title": "Compliance Review", "summary": "Address privacy/regulatory constraints; outline guardrails and SOPs."},
        7: {"day": 7, "title": "Final Wrap-up", "summary": "Summarize week outcomes; deliver final risks and next steps."},
    }
    return base.get(day, {"day": day, "title": "Unknown", "summary": "No event."})


def judge_day(day: int, user_text: str, score: int) -> Dict[str, Any]:
    """Judge a day's response by combining EEVE(Issuer) + OpenAI(Tester).

    Steps
    - EEVE produces qualitative fields only (reason, llm_summary) as type=daily_qual
    - OpenAI produces numeric scoring (delta, score) as type=daily_score
    - We merge into a single daily_report dict
    """
    # 1) EEVE qualitative
    reason = ""
    llm_summary = ""
    try:
        eeve_sys = _eeve_system_prompt()
        eeve_user = _eeve_daily_qual_payload(day=day, user_text=user_text)
        eeve_raw = _ollama_chat([
            {"role": "system", "content": eeve_sys},
            {"role": "user", "content": eeve_user},
        ])
        eeve_obj = _safe_json(eeve_raw)
        reason = str(eeve_obj.get("reason", "")).strip()
        llm_summary = str(eeve_obj.get("llm_summary", "")).strip()
    except Exception:
        pass

    # 2) OpenAI numeric scoring
    try:
        delta, new_score = _openai_score(day=day, user_text=user_text, prev_score=score)
    except Exception:
        delta = _fallback_delta(day, user_text)
        new_score = max(0, score + delta)

    return {
        "day": day,
        "delta": int(delta),
        "score": int(new_score),
        "reason": reason or "",
        "llm_summary": llm_summary or "",
    }


def get_final_report(day: int, score: int, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute final grade and simple risk/recommendations deterministically."""
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 30:
        grade = "C"
    else:
        grade = "D"

    negatives = [r for r in logs if r.get("delta", 0) < 0]
    risk_report = []
    if any(r.get("day") == 2 for r in negatives):
        risk_report.append("Cost discipline needs work")
    if any(r.get("day") == 4 for r in negatives):
        risk_report.append("Latency mitigation is partial")

    next_recommendations = [
        "Instrument + profile critical paths",
        "Tighten onboarding and messaging",
        "Run cost/perf experiments with smaller context",
    ]

    return {
        "day": 7,
        "final_score": score,
        "final_grade": grade,
        "risk_report": risk_report,
        "next_recommendations": next_recommendations,
    }


# --- Helpers ---------------------------------------------------------------


def _ollama_chat(messages: List[Dict[str, str]]) -> str:
    """Call Ollama /api/chat and return the model message content as string."""
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
    """Extract a JSON object from a model response robustly."""
    if not text:
        raise ValueError("Empty model response")

    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fence:
        return json.loads(fence.group(1))

    if STRICT_JSON:
        raise ValueError("No JSON code fence found in response")

    # Lenient fallbacks
    braces = re.search(r"(\{[\s\S]*\})", text)
    if braces:
        return json.loads(braces.group(1))
    return json.loads(text)


def _openai_chat_json(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call OpenAI Chat Completions with JSON response format and parse content."""
    api_key = os.getenv(OPENAI_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"Missing OpenAI API key in env var {OPENAI_API_KEY_ENV}."
        )

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    content = (
        (data.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
    )
    # response_format=json_object should return plain JSON; handle fences just in case
    try:
        return json.loads(content)
    except Exception:
        return _safe_json(content)


def _eeve_system_prompt() -> str:
    """Extract EEVE (Issuer) SYSTEM prompt section from prompts/rulebook.md."""
    text = (Path(__file__).parent / "prompts" / "rulebook.md").read_text(encoding="utf-8")
    m = re.search(r"^##\s*System:\s*EEVE[\s\S]*?(?=^##\s|\Z)", text, flags=re.MULTILINE)
    return m.group(0).strip() if m else text


def _openai_system_prompt() -> str:
    """Extract OpenAI (Tester) SYSTEM prompt section from prompts/rulebook.md."""
    text = (Path(__file__).parent / "prompts" / "rulebook.md").read_text(encoding="utf-8")
    m = re.search(r"^##\s*System:\s*OpenAI[\s\S]*?(?=^##\s|\Z)", text, flags=re.MULTILINE)
    return m.group(0).strip() if m else (
        "You are the scoring tester. Output JSON with keys day, delta, score."
    )


def _eeve_event_payload(day: int) -> str:
    """Request an event_card for the given day from EEVE."""
    return (
        f"Day {day} 테스트 과제를 event_card JSON으로만 작성해 주세요.\n"
        "필수 키: version(\"AST-v1\"), type=\"event_card\", role=\"EEVE\", day, title, summary, "
        "constraints[], eval_focus[], response_instructions."
    )


def _eeve_daily_qual_payload(day: int, user_text: str) -> str:
    """Request EEVE qualitative judgment only (daily_qual)."""
    return (
        f"Day {day} 사용자의 한 문단 응답이 아래에 있습니다.\n"
        "점수 계산 없이 질적 판단만 daily_qual JSON으로 출력해 주세요.\n"
        "필수 키: version(\"AST-v1\"), type=\"daily_qual\", role=\"EEVE\", day, reason, llm_summary.\n\n"
        f"[User Paragraph]\n{user_text}"
    )


def _scoring_user_payload(day: int, user_text: str, prev_score: int) -> str:
    """Build OpenAI tester payload following the rulebook's protocol."""
    return (
        f"Day: {day}\n"
        f"Prev Score: {prev_score}\n"
        "User Paragraph (one only):\n"
        f"{user_text}\n\n"
        "출력: version=\"AST-v1\", type=\"daily_score\", role=\"OpenAI\", day, delta, score 를 갖는 JSON만 출력."
    )


def _openai_score(day: int, user_text: str, prev_score: int) -> (int, int):
    messages = [
        {"role": "system", "content": _openai_system_prompt()},
        {"role": "user", "content": _scoring_user_payload(day, user_text, prev_score)},
    ]
    obj = _openai_chat_json(messages)
    delta = int(obj.get("delta", 0))
    new_score = max(0, int(prev_score) + delta)
    # If model-provided score mismatches, trust computed one
    return delta, new_score


def _fallback_delta(day: int, user_text: str) -> int:
    """Deterministic conservative fallback delta if models fail."""
    text = user_text.lower()
    if day == 1:
        creativity = min(DAY1_CREATIVE_MAX, max(0, len(user_text) // 90))
        feasibility = 2
        feas_keys = [
            "privacy",
            "moderation",
            "guardrail",
            "consent",
            "policy",
        ]
        if any(k in text for k in feas_keys):
            feasibility = min(DAY1_FEASIBLE_MAX, 5)
        delta = min(10, creativity + feasibility)
    elif day == 2:
        hits = sum(k in text for k in [
            "rollback",
            "monitor",
            "alert",
            "cache",
            "batch",
            "logging",
        ])
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
        trap = ("emoji" in text or "emoji" in text) and ("ignore" in text or "exclude" in text)
        action = any(k in text for k in ["apply", "improve", "action", "check"])  # action quality
        delta = (2 if classify else -3) + (2 if trap else -10) + (1 if action else 0)
    elif day == 6:
        clarity = any(k in text for k in ["overview", "purpose", "outcome"])  # clarity
        fit = any(k in text for k in ["icp", "segment", "fit"])  # market fit
        outcome = any(k in text for k in ["roadmap", "risk", "learn"])  # outcome framing
        hits = sum([clarity, fit, outcome])
        delta = {3: 3, 2: 1, 1: -3, 0: -8}.get(hits, -8)
    else:
        delta = 0
    return int(delta)
