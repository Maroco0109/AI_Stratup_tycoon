"""
Streamlit 메인 UI (고전 터미널 스타일)

역할
- 한 페이지에 하나의 `st.chat_input`만 사용합니다.
- engine.py를 통해 이벤트 카드 수신, 일일 채점/병합, 최종 보고서 생성을 수행합니다.
- 모델 출력(JSON)을 코드 블록으로 간결히 보여줍니다(확장 UI 사용 안 함).

설명
- 이 파일은 화면 구성과 사용자 입력 처리에만 집중합니다. 모델 호출/병합 로직은
  engine.py에 위임되며, 상태는 Streamlit session_state를 통해 공유됩니다.
"""

from __future__ import annotations

import json
import streamlit as st

from engine import get_event_card, judge_day, get_final_report  # type: ignore
from config import (  # type: ignore
    OLLAMA_BASE_URL,
    MODEL_NAME,
    OPENAI_MODEL,
    OPENAI_BASE_URL,
)
from prompts.templates import input_guidelines, input_example, RUBRIC_BY_DAY  # type: ignore
from log import log_daily, log_final, clear_logs  # type: ignore
from state import init_session_state  # type: ignore


# Page + classic terminal styling
st.set_page_config(page_title="AI Startup Tycoon — Local", page_icon="🧪", layout="wide")

st.markdown(
    """
    <style>
    :root { --term-fg:#33ff33; --term-bg:#000000; --term-border:#1a521a; }
    html, body, [data-testid=\"stAppViewContainer\"], [data-testid=\"stHeader\"] {
        background-color: var(--term-bg) !important; color: var(--term-fg) !important;
        font-family: \"Courier New\", Courier, monospace !important;
    }
    [data-testid=\"stSidebar\"] { background:var(--term-bg)!important; color:var(--term-fg)!important; border-right:1px solid var(--term-border); }
    h1,h2,h3,h4,h5,h6,p,label,code,pre { color:var(--term-fg)!important; font-family:\"Courier New\", Courier, monospace!important; }
    /* div는 아이콘 요소 제외하고 적용 */
    div:not([data-testid*="collapsedControl"]):not([class*="Icon"]) { color:var(--term-fg)!important; font-family:\"Courier New\", Courier, monospace!important; }
    /* Material Icons 제외 - 아이콘이 아닌 span만 타겟팅 */
    span:not([class*="material"]):not([data-baseweb]):not([aria-hidden]) { color:var(--term-fg)!important; font-family:\"Courier New\", Courier, monospace!important; }
    a{ color:var(--term-fg)!important; text-decoration:none; } a:hover{ text-decoration:underline; }
    [data-testid=\"stChatMessage\"]{ background:transparent!important; border:1px solid var(--term-border)!important; border-radius:0!important; padding:0.5rem 0.75rem!important; box-shadow:none!important; }
    [data-testid=\"stChatInput\"] textarea, [data-testid=\"stChatInput\"] div[contenteditable=\"true\"]{
        background:var(--term-bg)!important; color:var(--term-fg)!important; border:1px solid var(--term-border)!important; caret-color:var(--term-fg)!important;
        font-family:\"Courier New\", Courier, monospace!important; }
    .stButton > button{ background:var(--term-bg)!important; color:var(--term-fg)!important; border:1px solid var(--term-border)!important; border-radius:0!important; font-family:\"Courier New\", Courier, monospace!important; }
    .stButton > button:hover{ border-color:var(--term-fg)!important; }
    pre, code, .stCode code { background: var(--term-bg)!important; color: var(--term-fg)!important; border: none!important; }
    /* Material Icons와 아이콘 폰트는 원래 스타일 유지 - 더 강력하게 */
    [class*="material-icons"], [class*="Icon"], span[data-baseweb], span[aria-hidden="true"],
    button[data-testid*="collapsed"] *, [data-testid*="collapsedControl"] * {
        font-family: "Material Icons", "Material Symbols Outlined", system-ui !important;
    }
    /* 사이드바 토글 버튼 스타일 수정 */
    button[data-testid="baseButton-header"] {
        font-family: "Material Icons", "Material Symbols Outlined", system-ui !important;
    }
    /* keyboard_double_arrow 텍스트 숨기고 화살표 심볼로 대체 */
    button[data-testid="baseButton-header"] span {
        font-size: 0 !important; /* 원본 텍스트 숨김 */
    }
    button[data-testid="baseButton-header"] span::before {
        content: "»" !important; /* 사이드바 닫기 (오른쪽 화살표) */
        font-size: 1.5rem !important;
        font-family: monospace !important;
        color: var(--term-fg) !important;
        display: inline-block !important;
    }
    button[data-testid="baseButton-header"][aria-expanded="true"] span::before {
        content: "«" !important; /* 사이드바 열기 (왼쪽 화살표) */
    }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
------
AI Startup Tycoon [LOCAL]
Copyright (c) 1989-1993  AS-TYCO
------------------------------------------------------------
------
"""
)


# Session state (shared across pages)
init_session_state()

# Reset logs at first load of this Streamlit session (new tab or F5)
if "log_initialized" not in st.session_state:
    try:
        clear_logs()
    except Exception:
        pass
    st.session_state.log_initialized = True


# Sidebar status (text block)
with st.sidebar:
    st.markdown("------")
    st.markdown("STATUS")
    st.markdown("------")
    st.markdown(f"DAY:   {st.session_state.day} / 7")
    st.markdown(f"SCORE: {st.session_state.score}")
    st.markdown(f"GENERATOR: {MODEL_NAME} (EEVE)")
    st.markdown(f"SCORER:    {MODEL_NAME} (EEVE)")
    st.markdown("------")


def render_event_card(day: int):
    """해당 일차의 이벤트 카드를 표시합니다.

    - day<=6: EEVE(또는 결정론적 대체)에서 생성된 이벤트 카드(JSON)를 화면에 노출
    - day==7: 최종 보고 안내만 노출
    실패 시 최소 정보만 가진 대체 카드를 구성해 사용자에게 알립니다.
    """
    if day <= 6 and day not in st.session_state.event_card_by_day:
        try:
            st.session_state.event_card_by_day[day] = get_event_card(day)
        except Exception as e:
            st.session_state.last_error = f"Failed to load event card: {e}"
            st.session_state.event_card_by_day[day] = {
                "day": day,
                "title": "Event unavailable",
                "summary": "Unable to fetch event details. Please try again.",
            }

    if day <= 6:
        card = st.session_state.event_card_by_day.get(day, {})
        with st.chat_message("assistant"):
            title = card.get("title", "N/A")
            summary = card.get("summary", "")
            st.code(f"DAY {day} EVENT: {title}\n{summary}", language="text")
            st.code(json.dumps(card, ensure_ascii=False, indent=2), language="json")
    else:
        with st.chat_message("assistant"):
            st.code("FINAL DAY (7): Share your final strategy wrap-up.", language="text")


def render_input_help(day: int):
    """해당 일차에 맞는 가이드/루브릭/예시를 출력합니다.

    - Day 1: 창의적 아이디어 제시를 직접 문구로 안내
    - Day 2~6: prompts.templates에서 불러온 가이드/루브릭/예시 표시
    - Day 7: 최종 보고 안내
    """
    if 1 <= day <= 6:
        show_help = True
        if show_help:
            if day == 1:
                st.code("[GUIDELINE]\n창의적인 AI기반 사업 아이디어를 제시해주세요!", language="text")
            else:
                st.code(f"[GUIDELINE]\n{input_guidelines(day)}", language="text")
            rubric = RUBRIC_BY_DAY.get(day, "")
            if rubric:
                st.code(f"[RUBRIC]\n{rubric}", language="text")
            example = input_example(day)
            if example:
                st.code(f"입력 예시: {example}", language="text")
    elif day == 7:
        show_help = True
        if show_help:
            st.code("한 문단으로 일주일 전략 회고를 진행해주세요.", language="text")


def can_advance(day: int) -> bool:
    """다음 일차로 진행 가능한지 여부를 반환합니다.

    당일 리포트가 존재해야 다음 날로 넘어갈 수 있습니다.
    """
    return day in st.session_state.daily_report_by_day


# Flow
def render_previous_day_report(day: int):
    """이전 일차의 리포트를 간단한 코드 블록(JSON)으로 다시 보여줍니다."""
    prev = day - 1
    if prev >= 1 and prev in st.session_state.daily_report_by_day:
        with st.chat_message("assistant"):
            st.code(f"DAY {prev} REPORT", language="text")
            st.code(
                json.dumps(st.session_state.daily_report_by_day[prev], ensure_ascii=False, indent=2),
                language="json",
            )


render_previous_day_report(st.session_state.day)
render_event_card(st.session_state.day)
render_input_help(st.session_state.day)

# Capture current day snapshot for this interaction
current_day = st.session_state.day

user_text = st.chat_input("C:\\> 오늘의 한 문단을 입력해 주세요 _")

if user_text:
    with st.chat_message("user"):
        st.code(f"C\\DAY{current_day}> {user_text}", language="text")

    try:
        report = judge_day(current_day, user_text, st.session_state.score)

        if not isinstance(report, dict) or (
            current_day <= 6 and not all(
                k in report for k in ["day", "delta", "score", "reason", "llm_summary"]
            )
        ):
            raise ValueError("Engine returned malformed JSON for daily report.")

        # Remove unused tester fields from the view/state
        cleaned_report = dict(report)
        cleaned_report.pop("tester_reason", None)
        cleaned_report.pop("tester_llm_summary", None)

        st.session_state.logs.append(cleaned_report)
        st.session_state.score = cleaned_report.get("score", st.session_state.score)
        st.session_state.daily_report_by_day[current_day] = cleaned_report
        st.session_state.last_error = None

        # Log daily interaction (user input + model report)
        try:
            log_daily(page="app.py", day=current_day, user_text=user_text, report=cleaned_report, generator=MODEL_NAME, scorer=MODEL_NAME)
        except Exception:
            pass

        with st.chat_message("assistant"):
            st.code("DAILY REPORT RECEIVED", language="text")
            st.code(json.dumps(cleaned_report, ensure_ascii=False, indent=2), language="json")

        if current_day == 7:
            try:
                final_report = get_final_report(
                    day=current_day,
                    score=st.session_state.score,
                    logs=st.session_state.logs,
                )
                st.session_state.final_report = final_report
                show_final_json = True
                if show_final_json:
                    st.code(json.dumps(final_report, ensure_ascii=False, indent=2), language="json")
                # Log final summary
                try:
                    log_final(page="app.py", score=st.session_state.score, final_report=final_report, generator=MODEL_NAME, scorer=MODEL_NAME)
                except Exception:
                    pass
            except Exception as e:
                st.session_state.last_error = f"Failed to compute final report: {e}"

    except Exception as e:
        st.session_state.last_error = f"{e}"
        with st.chat_message("assistant"):
            st.error("Malformed or failed engine response. Please try again.")


# Next day button appears only after the day's report exists
if can_advance(st.session_state.day) and st.session_state.day < 7:
    cols = st.columns([1, 2, 1])
    with cols[1]:
        if st.button("[N] Next Day", key="next_day_after_report"):
            st.session_state.day += 1
            st.session_state.last_error = None
            st.rerun()

# Sticky errors
if st.session_state.last_error:
    st.info(st.session_state.last_error)
