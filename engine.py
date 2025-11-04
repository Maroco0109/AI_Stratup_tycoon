"""
Game orchestrator: daily events and scoring.

Change: OpenAI scores the user's input; EEVE (Ollama) handles qualitative
reasoning and summaries. We combine both into one daily report.

Functions
- get_event_card(day): deterministic event summary per day (1–6), wrap-up for 7
- judge_day(day, user_text, score):
    * Ask EEVE for qualitative fields (reason, llm_summary)
    * Ask OpenAI for numeric scoring (delta, score)
    * Merge and return strictly JSON-ready dict
- get_final_report(day, score, logs): compute final grade and simple suggestions

Implementation notes
- Ollama POST {OLLAMA_BASE_URL}/chat with messages [{role, content}, ...]
- OpenAI POST {OPENAI_BASE_URL}/chat/completions with response_format=json_object
- Robust JSON extraction via _safe_json
"""

from __future__ import annotations

import json
import os
import re
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
    OPENAI_BASE_URL,
    OPENAI_MODEL,
    OPENAI_API_KEY_ENV,
)
from prompts.templates import system_prompt, user_payload_judge


def get_event_card(day: int) -> Dict[str, Any]:
    """Return a simple event card for the given day.

    Currently deterministic to avoid latency and flakiness. You can switch to
    EEVE-based generation later if desired.
    """
    base = {
        1: {
            "day": 1,
            "title": "Idea Polishing",
            "summary": "Refine your AI startup idea: value prop, target users, and edge.",
        },
        2: {
            "day": 2,
            "title": "Obstacle: Cost Overruns",
            "summary": "Cloud inference costs spike. Propose immediate mitigations and a plan.",
        },
        3: {
            "day": 3,
            "title": "User Feedback",
            "summary": "Early testers are confused by onboarding. Clarify flows and messaging.",
        },
        4: {
            "day": 4,
            "title": "Performance Bottleneck",
            "summary": "Latency exceeds SLA. Describe profiling steps and prioritization.",
        },
        5: {
            "day": 5,
            "title": "Investor Meeting",
            "summary": "Craft a compelling pitch and metrics narrative for seed VCs.",
        },
        6: {
            "day": 6,
            "title": "Compliance Review",
            "summary": "Address privacy/regulatory constraints; outline guardrails and SOPs.",
        },
        7: {
            "day": 7,
            "title": "Final Wrap-up",
            "summary": "Summarize week outcomes; deliver final risks and next steps.",
        },
    }
    return base.get(day, {"day": day, "title": "Unknown", "summary": "No event."})


def judge_day(day: int, user_text: str, score: int) -> Dict[str, Any]:
    """Judge a day's response by combining EEVE(qualitative) + OpenAI(scoring).

    Steps
    - Get qualitative fields from EEVE (reason, llm_summary). If EEVE also emits
      delta/score per the global rulebook, we ignore those numeric fields.
    - Get numeric scoring from OpenAI (delta, score) per the game policy.
    - Merge and return a single daily_report dict.
    """
    # 1) EEVE for qualitative fields
    eeve_messages = [
        {"role": "system", "content": system_prompt()},
        {
            "role": "user",
            "content": user_payload_judge(day=day, user_text=user_text, prev_score=score),
        },
    ]

    reason = ""
    llm_summary = ""
    try:
        eeve_raw = _ollama_chat(eeve_messages)
        eeve_data = _safe_json(eeve_raw)
        reason = str(eeve_data.get("reason", "")).strip()
        llm_summary = str(eeve_data.get("llm_summary", "")).strip()
    except Exception:
        # Keep qualitative fields empty if EEVE fails; scoring still proceeds.
        pass

    # 2) OpenAI for numeric scoring
    try:
        delta, new_score = _openai_score(day=day, user_text=user_text, prev_score=score)
    except Exception:
        # Conservative deterministic fallback if OpenAI scoring fails
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


def _scoring_system_prompt() -> str:
    return (
        "You are the scoring judge for a 7-day AI startup game.\n"
        "Output strictly a JSON object with keys: day, delta, score.\n"
        "Rules:\n"
        "- Day 1: award +0..+5 for creativity and +0..+5 for feasibility; delta = sum (cap +10).\n"
        "- Day 2–6: allow penalties −5..−20 for weak responses; solid answers may be small positive or 0.\n"
        "- Score = prev_score + delta (do not go below 0).\n"
        "No extra commentary."
    )


def _scoring_user_payload(day: int, user_text: str, prev_score: int) -> str:
    return (
        f"Day: {day}\n"
        f"Prev score: {prev_score}\n"
        "User paragraph (one only):\n"
        f"{user_text}\n"
        "Return JSON only with keys: day, delta, score."
    )


def _openai_score(day: int, user_text: str, prev_score: int) -> (int, int):
    messages = [
        {"role": "system", "content": _scoring_system_prompt()},
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

