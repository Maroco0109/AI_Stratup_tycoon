"""
Engine: Orchestrates EEVE (Issuer) and OpenAI (Tester) per .
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

def _generate_summary_with_eeve(title: str) -> str:
    """EEVE로 title을 1문장으로 요약합니다. 실패 시 빈 문자열 반환."""
    print(f"[DEBUG] _generate_summary_with_eeve called with title: {title}")
    try:
        sys_prompt = "Summarize the title in 1 Korean sentence. Output only the summary, no extra text."
        user_prompt = f"Title: {title}\nSummary:"
        raw = _ollama_chat([
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ])
        summary = raw.strip()
        # 너무 길면 자르기
        if len(summary) > 200:
            summary = summary[:200]
        print(f"[DEBUG] Summary generated: {summary}")
        return summary
    except Exception as e:
        print(f"[ERROR] _generate_summary_with_eeve failed: {e}")
        return ""


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
    # Day 1-5: EEVE로 summary 생성
    if day == 1:
        title = "Day 1: AI 관련 사업 아이디어 제출"
        summary = _generate_summary_with_eeve(title) or "오늘은 창의적인 AI 기반 사업 아이디어를 수집합니다."
        return {
            "day": 1,
            "title": title,
            "summary": summary,
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
    if day == 2:
        title = "Day 2: 데이터 유출 위험 발생"
        summary = _generate_summary_with_eeve(title) or "학습된 모델 테스트 중, 개인 정보가 출력되는 현상이 발생했습니다."
        return {
            "day": 2,
            "title": title,
            "summary": summary,
            "constraints": [
                "한 문단으로만 작성해 주세요.",
                "한국어 존댓말을 사용해 주세요.",
            ],
            "eval_focus": [
                "실현 가능성(간단한 구현 경로)",
                "문제 해결 능력",
            ],
            "response_instructions": "데이터 유출 위험을 막을 수 있는 방법을 제시해주세요!",
        }
    if day == 3:
        title = "Day 3: 최근 1주간 API 요청이 증가했습니다. 이로 인해 API 요청 비용 예산 관리에 어려움이 발생했습니다."
        summary = _generate_summary_with_eeve(title) or "API 관련 예산 부족 현상이 발생했습니다."
        return {
            "day": 3,
            "title": title,
            "summary": summary,
            "constraints": [
                "한 문단으로만 작성해 주세요.",
                "한국어 존댓말을 사용해 주세요.",
            ],
            "eval_focus": [
                "실현 가능성(간단한 구현 경로)",
                "문제 해결 능력",
            ],
            "response_instructions": "증가한 API 요청에 대한 대응 방법을 제시해주세요!",
        }
    if day == 4:
        title = "Day 4: 모델 성능 관련 이슈가 발생했습니다. 추가 데이터를 활용하여 학습시킨 이후, 과적합 징후가 포착되었으며 실질 성능이 5% 가량 하락했습니다."
        summary = _generate_summary_with_eeve(title) or "모델 성능이 기존 대비 5%가량 하락했습니다."
        return {
            "day": 4,
            "title": title,
            "summary": summary,
            "constraints": [
                "한 문단으로만 작성해 주세요.",
                "한국어 존댓말을 사용해 주세요.",
            ],
            "eval_focus": [
                "실현 가능성(간단한 구현 경로)",
                "문제 해결 능력",
            ],
            "response_instructions": "과적합 징후를 해결하기 위한 방법을 제시해주세요!",
        }
    if day == 5:
        title = "Day 5: 사용자 피드백이 도착했습니다. - 모델이 너무 무거운거 같아요. 모델이 돌아갈 때, 기기에서 발열이 심해요. : 해당 피드백에 대한 적절한 답변을 제시하세요."
        summary = _generate_summary_with_eeve(title) or "모델 관련 사용자 피드백 - 기기 발열 문제"
        return {
            "day": 5,
            "title": title,
            "summary": summary,
            "constraints": [
                "한 문단으로만 작성해 주세요.",
                "한국어 존댓말을 사용해 주세요.",
            ],
            "eval_focus": [
                "실현 가능성(간단한 구현 경로)",
                "문제 해결 능력",
            ],
            "response_instructions": "모델 실행 시, 기기 발열 문제 해결을 위한 방법을 제시해주세요!",
        }
    # if 2 <= day <= 5:
    #     try:
    #         eeve_sys = _eeve_system_prompt_relaxed(day, mode="event")
    #         user = _eeve_event_payload_relaxed(day)
    #         raw = _ollama_chat([
    #             {"role": "system", "content": eeve_sys},
    #             {"role": "user", "content": user},
    #         ])
    #         obj = _safe_json(raw)
    #         if isinstance(obj, dict) and obj.get("type") == "event_card":
    #             return {
    #                 "day": int(obj.get("day", day)),
    #                 "title": obj.get("title") or f"Day {day} Event",
    #                 "summary": obj.get("summary") or "",
    #                 "constraints": obj.get("constraints", []),
    #                 "eval_focus": obj.get("eval_focus", []),
    #                 "response_instructions": obj.get("response_instructions", ""),
    #             }
    #     except Exception:
    #         pass

    # Day 6: EEVE로 summary 생성
    if day == 6:
        title = "Day 6: 투자자 피칭"
        summary = _generate_summary_with_eeve(title) or (
            "당신의 AI 스타트업을 한 문단으로 피칭하세요: 문제점과 고객, "
            "솔루션 및 AI/LLM 활용 방법(모델, 프롬프트/체인/RAG, 평가), 시장/세그먼트, "
            "경쟁 우위/컴플라이언스, 트랙션/지표 및 로드맵, 팀, 그리고 투자 요청(금액과 자금 사용 계획)을 포함해 주세요."
        )
        return {
            "day": 6,
            "title": title,
            "summary": summary,
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

    # Minimal fallback only when model generation fails (should not reach here for day 1-6)
    fallback_title = f"Day {day} Event (fallback)"
    fallback_summary = _generate_summary_with_eeve(fallback_title) or "모델이 이벤트 카드를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
    return {
        "day": day,
        "title": fallback_title,
        "summary": fallback_summary,
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
    # 1) EEVE qualitative (소형 모델용 간소화: 실패해도 무시)
    print(f"[DEBUG] judge_day called: day={day}, score={score}")
    reason = ""
    llm_summary = ""
    eeve_success = False  # EEVE 성공 여부 추적

    try:
        print("[DEBUG] Calling EEVE qualitative...")
        eeve_sys = _eeve_system_prompt_relaxed(day, mode="qual")
        eeve_user = _eeve_daily_qual_payload_clean(day=day, user_text=user_text)
        print(f"[DEBUG] EEVE system prompt: {eeve_sys[:100]}...")
        print(f"[DEBUG] EEVE user prompt: {eeve_user[:100]}...")

        eeve_raw = _ollama_chat([
            {"role": "system", "content": eeve_sys},
            {"role": "user", "content": eeve_user},
        ])

        print(f"[DEBUG] EEVE raw response length: {len(eeve_raw)}")
        print(f"[DEBUG] EEVE raw response preview: {eeve_raw[:200]}...")

        if not eeve_raw or len(eeve_raw.strip()) == 0:
            # 빈 응답 - fallback 사용
            print("[DEBUG] EEVE returned empty response")
            pass
        else:
            # 더 관대한 JSON 파싱 시도
            try:
                eeve_obj = _safe_json(eeve_raw)
                reason = str(eeve_obj.get("reason", "")).strip()
                llm_summary = str(eeve_obj.get("llm_summary", "")).strip()
                print(f"[DEBUG] EEVE parsed JSON - reason: {reason[:50]}..., llm_summary: {llm_summary[:50]}...")
                if reason or llm_summary:
                    eeve_success = True
                    reason = f"[EEVE] {reason}" if reason else ""
                    llm_summary = f"[EEVE] {llm_summary}" if llm_summary else ""
            except Exception as e:
                print(f"[DEBUG] EEVE JSON parsing failed: {e}")
                # JSON 파싱 실패 시 raw 텍스트에서 추출 시도
                if eeve_raw and len(eeve_raw) > 0:
                    if "keywords found" in eeve_raw.lower() or "good" in eeve_raw.lower():
                        reason = f"[EEVE-Raw] {eeve_raw[:100]}"
                        llm_summary = "[EEVE-Raw] 평가 완료"
                        eeve_success = True
                        print("[DEBUG] EEVE used raw text fallback")
                # 그래도 실패하면 빈 문자열 유지 (fallback이 채움)
    except Exception as e:
        # EEVE 호출 실패는 치명적이지 않음 (tester fallback이 있음)
        print(f"[ERROR] EEVE qualitative failed: {e}")
        pass

    # 2) OpenAI numeric scoring (+ tester qualitative when present)
    # 초기화: 최악의 경우를 대비
    delta = 0
    new_score = score
    tester_reason = ""
    tester_llm_summary = ""
    scorer_type = ""  # 채점 모델 추적

    try:
        print("[DEBUG] Calling OpenAI/EEVE scorer...")
        oai_obj = _openai_score(day=day, user_text=user_text, prev_score=score)
        delta = int(oai_obj.get("delta", 0))
        new_score = max(0, score + delta)
        tester_reason = str(oai_obj.get("reason", "")).strip()
        tester_llm_summary = str(oai_obj.get("llm_summary", "")).strip()
        scorer_type = "OpenAI/EEVE"
        print(f"[DEBUG] Scorer success - delta: {delta}, new_score: {new_score}")
        if tester_reason:
            tester_reason = f"[{scorer_type}] {tester_reason}"
        if tester_llm_summary:
            tester_llm_summary = f"[{scorer_type}] {tester_llm_summary}"
    except Exception as e:
        print(f"[DEBUG] OpenAI scorer failed: {e}, trying fallback...")
        # Prompt-engineered LLM fallback first (semantic, rubric-based; avoids keyword hits)
        try:
            print("[DEBUG] Trying fallback LLM scorer...")
            fb = _fallback_llm_score(day=day, user_text=user_text, prev_score=score)
            delta = int(fb.get("delta", 0))
            new_score = max(0, score + delta)
            tester_reason = str(fb.get("reason", "")).strip()
            tester_llm_summary = str(fb.get("llm_summary", "")).strip()
            scorer_type = "Fallback-LLM"
            print(f"[DEBUG] Fallback-LLM success - delta: {delta}, new_score: {new_score}")
            if tester_reason:
                tester_reason = f"[{scorer_type}] {tester_reason}"
            if tester_llm_summary:
                tester_llm_summary = f"[{scorer_type}] {tester_llm_summary}"
        except Exception as e:
            print(f"[DEBUG] Fallback-LLM failed: {e}, trying keyword fallback...")
            # Deterministic last-resort fallback (kept for robustness)
            try:
                fb_result = _fallback_delta(day, user_text)
                delta = int(fb_result.get("delta", 0))
                new_score = max(0, score + delta)
                tester_reason = str(fb_result.get("reason", "")).strip()
                tester_llm_summary = str(fb_result.get("llm_summary", "")).strip()
                scorer_type = "Keyword"
                print(f"[DEBUG] Keyword fallback success - delta: {delta}, new_score: {new_score}")
                if tester_reason:
                    tester_reason = f"[{scorer_type}] {tester_reason}"
                if tester_llm_summary:
                    tester_llm_summary = f"[{scorer_type}] {tester_llm_summary}"
            except Exception as e:
                print(f"[ERROR] All scorers failed: {e}")
                # 최후의 안전망: _fallback_delta도 실패하면 0점 유지
                delta = 0
                new_score = score
                scorer_type = "Error"
                tester_reason = "[Error] 평가 실패 (모든 채점 시스템 오류)"
                tester_llm_summary = "[Error] 시스템 오류로 인해 채점을 완료할 수 없습니다."

    # EEVE qualitative가 실패한 경우 fallback의 reason/llm_summary를 사용
    # (tester의 값은 이미 모델 태그가 붙어있음)
    if not eeve_success:
        if not reason and tester_reason:
            reason = tester_reason
        if not llm_summary and tester_llm_summary:
            llm_summary = tester_llm_summary

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
        "stream": False,  # 명시적으로 스트리밍 비활성화
    }

    # 디버그 로깅
    print(f"[DEBUG] Ollama chat URL: {url}")
    print(f"[DEBUG] Model: {MODEL_NAME}")
    print(f"[DEBUG] Messages: {messages[:1]}...")  # 첫 메시지만 출력

    try:
        r = requests.post(url, json=payload, timeout=60)
        print(f"[DEBUG] Status code: {r.status_code}")
        r.raise_for_status()
        data = r.json()

        # 응답 구조 로깅
        print(f"[DEBUG] Response keys: {data.keys() if isinstance(data, dict) else 'list'}")

        if isinstance(data, dict) and "message" in data:
            content = data["message"].get("content", "")
            print(f"[DEBUG] Content length: {len(content)}")
            print(f"[DEBUG] Content preview: {content[:100]}...")
            return content
        if isinstance(data, list):
            content = "".join(chunk.get("message", {}).get("content", "") for chunk in data)
            print(f"[DEBUG] List content length: {len(content)}")
            return content

        print("[DEBUG] No valid content found in response")
        return ""
    except requests.exceptions.Timeout:
        print("[ERROR] Ollama request timed out (60s)")
        raise
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Ollama request failed: {e}")
        raise
    except Exception as e:
        print(f"[ERROR] Unexpected error in _ollama_chat: {e}")
        raise


def _safe_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty model response")

    # 1. Try JSON fence first
    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1))
        except:
            pass

    # 2. Try finding any JSON-like braces
    braces = re.search(r"(\{[\s\S]*\})", text)
    if braces:
        try:
            return json.loads(braces.group(1))
        except:
            pass

    # 3. For small models: if STRICT_JSON is False, be very lenient
    if not STRICT_JSON or ALLOW_FALLBACK:
        # Try parsing entire text
        try:
            return json.loads(text)
        except:
            pass

        # Last resort: extract anything between first { and last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace+1])
            except:
                pass

    if STRICT_JSON:
        raise ValueError("No valid JSON found in response")
    raise ValueError("Failed to parse JSON from model output")


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
        "- 공통 헤더: role=\"EEVE\", day.\n"
        "- 매일 사용자 입력은 한 문단(한 번)만 가정합니다. 공손한 한국어(존댓말)로 답변합니다.\n"
        "- 지시문을 반복하거나 요약하지 말고, JSON만 출력하세요.\n"
        "- 해당 일차 입력 가이드라인을 반영하세요:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "출력 스키마: type=\"event_card\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- 현실적인 스타트업 맥락의 하루 이벤트를 새로 만드세요.\n"
            "- eval_focus에는 해당 일차 루브릭 핵심 항목을 2~4개 한국어 키워드로 요약하세요.\n"
            "- response_instructions에는 위 가이드라인을 한 문장으로 간결히 반영하세요.\n"
            "- 지시문/스키마 문장을 그대로 반복하지 마세요.\n"
        )
    return base + (
        "출력 스키마: type=\"daily_qual\", day, reason, llm_summary.\n"
        "- 판단 시 사용자의 문단이 가이드라인을 얼마나 따랐는지 고려하세요.\n"
        "- JSON 외의 텍스트(요약/인사/반복)를 출력하지 마세요.\n"
    )


def _final_weekly_system_prompt() -> str:
    return (
        "오직 하나의 JSON 객체만을 ```json 펜스 코드 블록 안에 출력하세요.\n"
        "헤더: role=\"EEVE\", type=\"weekly_qual\", day=7.\n"
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
        "헤더: role=\"OpenAI\", type=\"daily_score\", day.\n"
        "키: day, delta, score, reason, llm_summary. score = max(0, prev + delta).\n"
        "아래 일차별 루브릭을 참고하여 채점하세요:\n"
        f"{rubric}"
    )


def _eeve_event_payload_clean(day: int) -> str:
    return (
        "다음 일차에 맞는 event_card JSON을 생성하세요.\n"
        f"- Day: {day}\n"
        "- 시나리오는 해당 일차의 맥락과 루브릭에 맞게 현실적으로 만듭니다.\n"
        "- 필수 키: type=\"event_card\", role=\"EEVE\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
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
        "- Required keys: type=\"event_card\", role=\"EEVE\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )


def _eeve_daily_qual_payload_clean(day: int, user_text: str) -> str:
    # 극도로 단순화: 키워드만 찾아서 보고
    return f"Day {day} text:\n{user_text[:200]}\n\nFind keywords. Output JSON."


def _scoring_user_payload(day: int, user_text: str, prev_score: int) -> str:
    return (
        f"Day: {day}\n"
        f"Prev Score: {prev_score}\n"
        "User Paragraph (one only):\n"
        f"{user_text}\n\n"
        "Output schema: \"\", type=\"daily_score\", role=\"OpenAI\", day, delta, score, reason, llm_summary."
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

    - Keeps  JSON contract but emphasizes semantic, rubric-based evaluation.
    - Avoids keyword-hit heuristics; clamps delta implicitly via rubric instructions.
    - If anything fails, caller should revert to deterministic _fallback_delta.
    """
    rubric = RUBRIC_BY_DAY.get(day, "")
    sys = (
        "Return exactly one JSON object (no extra text) inside one ```json fenced block.\n"
        "Header: role=\"EEVE\", type=\"daily_score\", day.\n"
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
        "Output schema: type=\"daily_score\", role=\"OpenAI\", day, delta, score, reason, llm_summary."
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

def _fallback_delta(day: int, user_text: str) -> Dict[str, Any]:
    """결정론적 점수 증감(delta) 계산기.

    - 단순 키워드 존재 여부와 조합으로 휴리스틱한 가/감점을 적용합니다.
    - 각 일차별로 핵심 요소를 최소화하여 점수 흐름의 일관성을 보장합니다.
    - reason과 llm_summary도 함께 반환합니다.
    """
    text = user_text.lower()
    reason = ""
    llm_summary = ""

    if day == 1:
        keywords = ["개인정보", "프라이버시", "모더레이션", "검열", "가드레일", "안전장치", "동의", "정책", "타겟", "목표", "ai", "llm", "rag"]
        found_keywords = [k for k in keywords if k in text]

        creativity = min(DAY1_CREATIVE_MAX, max(0, len(user_text) // 90))
        feasibility = 2
        if found_keywords:
            feasibility = min(DAY1_FEASIBLE_MAX, 5)
        delta = min(10, creativity + feasibility)

        if found_keywords:
            reason = f"창의성 점수 {creativity}점, 실현가능성 {feasibility}점을 획득했습니다. 발견된 핵심 요소: {', '.join(found_keywords[:3])}"
            llm_summary = f"AI 기반 사업 아이디어가 구체적이며, 개인정보 보호 및 안전장치 관련 고려사항을 포함하고 있습니다."
        else:
            reason = f"창의성 점수 {creativity}점, 실현가능성 {feasibility}점을 획득했습니다. 기술적 세부사항 보완이 필요합니다."
            llm_summary = f"아이디어는 제시되었으나 AI/LLM 활용 방안, 프라이버시 정책 등 구체적인 기술적 고려사항이 부족합니다."

    elif day == 2:
        keywords = ["롤백", "복구", "모니터링", "감시", "알림", "경보", "캐시", "로깅", "기록", "유출", "마스킹", "보호", "서버"]
        found_keywords = [k for k in keywords if k in text]
        hits = len(found_keywords)
        delta = 0 if hits >= 0 else -10

        if hits >= 5:
            reason = f"데이터 유출 대응책이 충분히 제시되었습니다. 발견된 대응 방안: {', '.join(found_keywords[:5])}"
            llm_summary = "복구 전략, 모니터링, 보호 조치 등 포괄적인 데이터 유출 대응 방안을 제시했습니다."
        elif hits >= 3:
            reason = f"일부 대응책이 제시되었으나 보완이 필요합니다. 발견된 대응 방안: {', '.join(found_keywords)}"
            llm_summary = "기본적인 대응 방안은 있으나 모니터링, 로깅, 보호 조치 등 추가적인 안전장치가 필요합니다."
        else:
            reason = f"데이터 유출 대응책이 불충분합니다. 발견된 대응 방안: {', '.join(found_keywords) if found_keywords else '없음'}"
            llm_summary = "데이터 유출 문제에 대한 구체적인 기술적 대응책(롤백, 모니터링, 마스킹 등)이 누락되었습니다."

    elif day == 3:
        keywords = ["적합", "풋프린트", "용량", "컨텍스트", "맥락", "길이", "모델", "디도스", "ddos", "잘못된 요청"]
        found_keywords = [k for k in keywords if k in text]
        fit = len(found_keywords) > 0
        delta = (0 if fit else -5)

        if fit:
            reason = f"API 비용 증가 원인 분석이 적절합니다. 발견된 분석 요소: {', '.join(found_keywords)}"
            llm_summary = "API 요청 증가에 대한 기술적 원인(모델 크기, 컨텍스트 길이 등)을 파악하고 있습니다."
        else:
            reason = "API 비용 증가 원인에 대한 기술적 분석이 부족합니다."
            llm_summary = "모델 용량, 컨텍스트 길이, 요청 패턴 등 구체적인 기술적 원인 분석이 필요합니다."

    elif day == 4:
        keywords = ["과적합", "정규화", "l2", "l1", "활성화 함수", "활성화함수", "드롭아웃", "하이퍼파라미터", "하이퍼 파라미터", "파라미터", "매개변수", "데이터", "증강", "증대"]
        found_keywords = [k for k in keywords if k in text]
        hits = len(found_keywords) > 0
        delta = (0 if hits else -5)

        if hits:
            reason = f"과적합 해결 방안이 제시되었습니다. 발견된 해결 방안: {', '.join(found_keywords[:4])}"
            llm_summary = "정규화, 드롭아웃, 데이터 증강 등 과적합 완화를 위한 기술적 접근법을 제시했습니다."
        else:
            reason = "과적합 문제에 대한 구체적인 해결 방안이 부족합니다."
            llm_summary = "정규화 기법, 하이퍼파라미터 조정, 데이터 증강 등 과적합 완화 방안이 누락되었습니다."

    elif day == 5:
        keywords = ["양자화", "크기", "파라미터", "매개변수", "변경", "교체", "모델"]
        found_keywords = [k for k in keywords if k in text]
        hits = len(found_keywords) > 0
        delta = (0 if hits else -5)

        if hits:
            reason = f"모델 발열 문제 해결책이 제시되었습니다. 발견된 해결책: {', '.join(found_keywords)}"
            llm_summary = "모델 경량화, 양자화, 파라미터 조정 등 발열 문제 해결을 위한 기술적 방안을 제시했습니다."
        else:
            reason = "모델 발열 문제에 대한 기술적 해결책이 부족합니다."
            llm_summary = "양자화, 모델 크기 조정, 경량 모델 교체 등 구체적인 최적화 방안이 필요합니다."

    elif day == 6:
        # Investor pitch coverage heuristic
        categories = {
            "문제 및 고객": ["문제", "고객", "페인포인트", "고충"],
            "AI/LLM 활용": ["ai", "llm", "모델", "rag", "프롬프트", "평가"],
            "시장 및 경쟁우위": ["시장", "세그먼트", "구간", "해자", "경쟁우위", "개인정보", "프라이버시", "컴플라이언스", "규정준수", "안전"],
            "트랙션 및 로드맵": ["트랙션", "견인력", "지표", "kpi", "파일럿", "시범", "mrr", "사용자", "로드맵"],
            "팀 및 투자 요청": ["팀", "요청", "펀딩", "투자", "자금 사용", "예산"]
        }

        covered_categories = []
        for cat_name, cat_keywords in categories.items():
            if any(k in text for k in cat_keywords):
                covered_categories.append(cat_name)

        g_problem = any(k in text for k in categories["문제 및 고객"])
        g_solution_ai = any(k in text for k in categories["AI/LLM 활용"])
        g_market_moat = any(k in text for k in categories["시장 및 경쟁우위"])
        g_traction = any(k in text for k in categories["트랙션 및 로드맵"])
        g_team_ask = any(k in text for k in categories["팀 및 투자 요청"])

        coverage = sum([g_problem, g_solution_ai, g_market_moat, g_traction, g_team_ask])
        delta = {5: 5, 4: 3, 3: 1, 2: -3, 1: -5, 0: -8}.get(coverage, -8)

        if coverage >= 4:
            reason = f"투자 피칭이 포괄적입니다. 포함된 항목({coverage}/5): {', '.join(covered_categories)}"
            llm_summary = "문제 정의, AI 활용, 시장 분석, 트랙션, 투자 요청 등 투자자가 원하는 핵심 정보를 충실히 제공했습니다."
        elif coverage >= 2:
            reason = f"투자 피칭이 부분적입니다. 포함된 항목({coverage}/5): {', '.join(covered_categories)}"
            missing = [cat for cat in categories.keys() if cat not in covered_categories]
            llm_summary = f"일부 항목이 누락되었습니다. 추가 필요: {', '.join(missing[:2])}"
        else:
            reason = f"투자 피칭이 불충분합니다. 포함된 항목({coverage}/5): {', '.join(covered_categories) if covered_categories else '없음'}"
            llm_summary = "투자자 피칭에 필수적인 문제/고객, AI 활용, 시장, 트랙션, 팀/투자요청 정보가 대부분 누락되었습니다."
    else:
        delta = 0
        reason = "해당 일차에 대한 평가 기준이 없습니다."
        llm_summary = ""

    return {
        "delta": int(delta),
        "reason": reason,
        "llm_summary": llm_summary,
    }


# --- Relaxed prompt builders (additive, used by call sites) ---------------

def _eeve_system_prompt_relaxed(day: int, mode: str) -> str:
    """A lighter system prompt that preserves  and JSON-fence rules
    while giving the model freedom in event style and content.
    """
    if mode == "qual":
        # 극도로 단순화된 프롬프트: 키워드 검출만
        return (
            "JSON output only.\n"
            "Format: {\"reason\": \"keywords found: X, Y\" or \"no keywords\", \"llm_summary\": \"good\" or \"needs improvement\"}\n"
            "Keep it very short."
        )

    guideline = input_guidelines(day) or ""
    base = (
        "아래 최소 규칙만 지켜 주세요.\n"
        "- 단 하나의 JSON 객체를 하나의 ```json 펜스 블록 안에만 출력합니다.\n"
        "- 펜스 밖 텍스트/이모지/주석/반복은 금지합니다.\n"
        "- 헤더 키: role=\"EEVE\", day.\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "스키마: type=\"event_card\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- 사건/상황/기회 등 어떤 형식이든 자유롭게 제시해도 됩니다(현실적이면 충분).\n"
            "- summary는 1문장\n"
            "- eval_focus는 1개 짧은 초점(형식 자유).\n"
            "- response_instructions는 한 문장으로 한 문단 답변을 부드럽게 요청하세요.\n"
        )
    return base


def _eeve_event_payload_relaxed(day: int) -> str:
    """Minimal user payload to elicit a freer event card while keeping schema."""
    return (
        "다음 조건으로 event_card(JSON)를 출력해 주세요.\n"
        f"- Day: {day}\n"
        # "- 사업의 사건을 창의적으로 제시합니다(수치 선택).\n"
        "- 사업의 사건을 제시합니다(수치 선택).\n"
        "- 필수 키: type=\"event_card\", role=\"EEVE\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- 반드시 하나의 ```json 펜스 안에 단일 JSON 객체만 출력하세요."
    )
