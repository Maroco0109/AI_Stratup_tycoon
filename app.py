"""
Streamlit main UI (classic terminal style)

- One st.chat_input per page
- Uses engine.py for events, judging, and final report
- Displays JSON via checkbox toggles (no expanders)
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
from prompts.templates import input_guidelines, input_example  # type: ignore


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
    h1,h2,h3,h4,h5,h6,p,span,label,div,code,pre { color:var(--term-fg)!important; font-family:\"Courier New\", Courier, monospace!important; }
    a{ color:var(--term-fg)!important; text-decoration:none; } a:hover{ text-decoration:underline; }
    [data-testid=\"stChatMessage\"]{ background:transparent!important; border:1px solid var(--term-border)!important; border-radius:0!important; padding:0.5rem 0.75rem!important; box-shadow:none!important; }
    [data-testid=\"stChatInput\"] textarea, [data-testid=\"stChatInput\"] div[contenteditable=\"true\"]{
        background:var(--term-bg)!important; color:var(--term-fg)!important; border:1px solid var(--term-border)!important; caret-color:var(--term-fg)!important;
        font-family:\"Courier New\", Courier, monospace!important; }
    .stButton > button{ background:var(--term-bg)!important; color:var(--term-fg)!important; border:1px solid var(--term-border)!important; border-radius:0!important; font-family:\"Courier New\", Courier, monospace!important; }
    .stButton > button:hover{ border-color:var(--term-fg)!important; }
    pre, code, .stCode code { background: var(--term-bg)!important; color: var(--term-fg)!important; border: none!important; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
```
AI Startup Tycoon [LOCAL]
Copyright (c) 1989-1993  AS-TYCO
------------------------------------------------------------
```
"""
)


# Session state
if "day" not in st.session_state:
    st.session_state.day = 1
if "score" not in st.session_state:
    st.session_state.score = 100
if "logs" not in st.session_state:
    st.session_state.logs: list[dict] = []
if "daily_report_by_day" not in st.session_state:
    st.session_state.daily_report_by_day = {}
if "event_card_by_day" not in st.session_state:
    st.session_state.event_card_by_day = {}
if "final_report" not in st.session_state:
    st.session_state.final_report = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None


# Sidebar status (text block)
with st.sidebar:
    st.markdown("```")
    st.markdown("STATUS")
    st.markdown("------")
    st.markdown(f"DAY:   {st.session_state.day} / 7")
    st.markdown(f"SCORE: {st.session_state.score}")
    st.markdown(f"GENERATOR: {MODEL_NAME} @ {OLLAMA_BASE_URL}")
    st.markdown(f"SCORER:    {OPENAI_MODEL} @ {OPENAI_BASE_URL}")
    st.markdown("```")


def render_event_card(day: int):
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
            show_event_json = st.checkbox("[+] Show Event JSON", key=f"event_json_{day}")
            if show_event_json:
                st.code(json.dumps(card, ensure_ascii=False, indent=2), language="json")
    else:
        with st.chat_message("assistant"):
            st.code("FINAL DAY (7): Share your final strategy wrap-up.", language="text")


def render_input_help(day: int):
    if 1 <= day <= 6:
        show_help = st.checkbox("[?] Show Input Help", key=f"input_help_{day}")
        if show_help:
            st.code(f"형식 요약: {input_guidelines(day)}", language="text")
            example = input_example(day)
            if example:
                st.code(example, language="text")
    elif day == 7:
        show_help = st.checkbox("[?] Show Input Help", key="input_help_7")
        if show_help:
            st.code("한 문단으로 일주일 전략 회고 및 다음 계획을 요약해 주세요.", language="text")


def can_advance(day: int) -> bool:
    return day in st.session_state.daily_report_by_day


# Flow
render_event_card(st.session_state.day)
render_input_help(st.session_state.day)

user_text = st.chat_input("C:\\> 오늘의 한 문단을 입력해 주세요 _")

if user_text:
    with st.chat_message("user"):
        st.code(f"C:\\DAY{st.session_state.day}> {user_text}", language="text")

    try:
        report = judge_day(st.session_state.day, user_text, st.session_state.score)

        if not isinstance(report, dict) or (
            st.session_state.day <= 6 and not all(
                k in report for k in ["day", "delta", "score", "reason", "llm_summary"]
            )
        ):
            raise ValueError("Engine returned malformed JSON for daily report.")

        st.session_state.logs.append(report)
        st.session_state.score = report.get("score", st.session_state.score)
        st.session_state.daily_report_by_day[st.session_state.day] = report
        st.session_state.last_error = None

        with st.chat_message("assistant"):
            st.code("DAILY REPORT RECEIVED", language="text")
            show_daily_json = st.checkbox(
                "[+] Show Daily JSON (report)", key=f"daily_json_{st.session_state.day}", value=True
            )
            if show_daily_json:
                st.code(json.dumps(report, ensure_ascii=False, indent=2), language="json")

        if st.session_state.day == 7:
            try:
                final_report = get_final_report(
                    day=st.session_state.day,
                    score=st.session_state.score,
                    logs=st.session_state.logs,
                )
                st.session_state.final_report = final_report
                show_final_json = st.checkbox("[+] Show Final Report", key="final_json", value=True)
                if show_final_json:
                    st.code(json.dumps(final_report, ensure_ascii=False, indent=2), language="json")
            except Exception as e:
                st.session_state.last_error = f"Failed to compute final report: {e}"

    except Exception as e:
        st.session_state.last_error = f"{e}"
        with st.chat_message("assistant"):
            st.error("Malformed or failed engine response. Please try again.")


# Next day button
cols = st.columns([1, 2, 1])
with cols[1]:
    advance_disabled = not can_advance(st.session_state.day) or st.session_state.day >= 7
    if st.button("[N] Next Day", disabled=advance_disabled):
        if st.session_state.day < 7:
            st.session_state.day += 1
            st.session_state.last_error = None


# Sticky errors
if st.session_state.last_error:
    st.info(st.session_state.last_error)

