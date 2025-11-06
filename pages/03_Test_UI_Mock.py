"""
Streamlit UI 테스트 페이지(모의)

목적
- 엔진을 호출하지 않고 채팅형 GUI를 미리 확인합니다.
- 페이지당 하나의 `st.chat_input` 제약을 지킵니다.
- `app.py` 레이아웃을 모사합니다: 사이드바 상태, 이벤트 카드, 입력 가이드,
  일일 JSON 보고서, 다음 날 버튼, 최종 보고(선택) 등.
"""

from __future__ import annotations

import streamlit as st


st.set_page_config(page_title="AI Startup Tycoon — Test UI", page_icon="🧪", layout="wide")

# Classic CMD aesthetic: green on black, monospace
st.markdown(
    """
    <style>
    :root {
        --term-fg: #33ff33;
        --term-dim: #228B22;
        --term-bg: #000000;
        --term-border: #1a521a;
    }
    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: var(--term-bg) !important;
        color: var(--term-fg) !important;
        font-family: "Courier New", Courier, monospace !important;
    }
    [data-testid="stSidebar"] {
        background-color: var(--term-bg) !important;
        color: var(--term-fg) !important;
        border-right: 1px solid var(--term-border);
    }
    h1, h2, h3, h4, h5, h6, p, span, label, div, code, pre {
        color: var(--term-fg) !important;
        font-family: "Courier New", Courier, monospace !important;
    }
    a { color: var(--term-fg) !important; text-decoration: none; }
    a:hover { text-decoration: underline; }
    /* Chat bubbles */
    [data-testid="stChatMessage"] {
        background: transparent !important;
        border: 1px solid var(--term-border) !important;
        border-radius: 0 !important;
        padding: 0.5rem 0.75rem !important;
        box-shadow: none !important;
    }
    /* Chat input */
    [data-testid="stChatInput"] textarea {
        background: var(--term-bg) !important;
        color: var(--term-fg) !important;
        border: 1px solid var(--term-border) !important;
        caret-color: var(--term-fg) !important;
        font-family: "Courier New", Courier, monospace !important;
    }
    [data-testid="stChatInput"] div[contenteditable="true"] {
        background: var(--term-bg) !important;
        color: var(--term-fg) !important;
        border: 1px solid var(--term-border) !important;
        caret-color: var(--term-fg) !important;
        font-family: "Courier New", Courier, monospace !important;
    }
    /* Buttons */
    .stButton > button {
        background: var(--term-bg) !important;
        color: var(--term-fg) !important;
        border: 1px solid var(--term-border) !important;
        border-radius: 0 !important;
        font-family: "Courier New", Courier, monospace !important;
    }
    .stButton > button:hover { border-color: var(--term-fg) !important; }
    /* Expander */
    [data-testid="stExpander"] details {
        background: var(--term-bg) !important;
        border: 1px solid var(--term-border) !important;
    }
    /* Hide expander default arrow/marker and icon text */
    [data-testid="stExpander"] details > summary { list-style: none !important; }
    [data-testid="stExpander"] details > summary::marker { content: "" !important; }
    [data-testid="stExpander"] summary svg { display: none !important; }
    [data-testid="stExpander"] summary [data-testid="stExpanderToggleIcon"] { display: none !important; }
    [data-testid="stExpander"] summary span[aria-hidden="true"] { display: none !important; }
    [data-testid="stMetricValue"], [data-testid="stMetricDelta"] { color: var(--term-fg) !important; }
    /* Code blocks */
    pre, code, .stCode code {
        background: var(--term-bg) !important;
        color: var(--term-fg) !important;
        border: none !important;
    }
    /* Hide Streamlit footer */
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("""
            ```
AI Startup Tycoon [TEST UI]
Copyright (c) 1989-1993  AS-TYCO
------------------------------------------------------------
""")


# Session bootstrap (aligned with app.py keys)
if "day" not in st.session_state:
    st.session_state.day = 1
if "score" not in st.session_state:
    st.session_state.score = 100
if "logs" not in st.session_state:
    st.session_state.logs = []
if "daily_report_by_day" not in st.session_state:
    st.session_state.daily_report_by_day = {}
if "event_card_by_day" not in st.session_state:
    st.session_state.event_card_by_day = {}
if "final_report" not in st.session_state:
    st.session_state.final_report = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None


def _mock_event_card(day: int) -> dict:
    # Deterministic sample card to preview layout
    return {
        "version": "AST-v1",
        "type": "event_card",
        "role": "issuer",
        "day": day,
        "title": f"Day {day} funding and growth trade-off",
        "summary": "Choose between growth spend vs runway extension; reply in one paragraph.",
        "constraints": {
            "language": "ko-KR (polite)",
            "length": "one paragraph",
        },
    }


def _mock_daily_report(day: int, prev_score: int) -> dict:
    # Simple, readable deterministic delta: +7 on odd days, -3 on even days.
    delta = 7 if day % 2 == 1 else -3
    score = max(0, prev_score + delta)
    return {
        "version": "AST-v1",
        "type": "daily",
        "role": "mock",
        "day": day,
        "delta": delta,
        "score": score,
        "reason": "모의 평가입니다. 실제 점수 로직 없이 UI 미리보기용입니다.",
        "llm_summary": "하루 전략 요약(모의). 비용 대비 성과를 고려해 실행합니다.",
    }


def _mock_final_report(day: int, score: int, logs: list[dict]) -> dict:
    return {
        "version": "AST-v1",
        "type": "final",
        "role": "mock",
        "day": day,
        "final_score": score,
        "grade": "A" if score >= 120 else ("B" if score >= 100 else "C"),
        "summary": "모의 최종 리포트입니다. 실제 엔진 없이 UI만 검증합니다.",
        "days": [
            {"day": r.get("day"), "delta": r.get("delta"), "score": r.get("score")} for r in logs
        ],
    }


def render_event_card(day: int):
    if day <= 6 and day not in st.session_state.event_card_by_day:
        st.session_state.event_card_by_day[day] = _mock_event_card(day)

    if day <= 6:
        card = st.session_state.event_card_by_day.get(day, {})
        with st.chat_message("assistant"):
            st.markdown(
                f"------")
            st.markdown(
                f"DAY {day} EVENT: {card.get('title', 'N/A')}\n"
                f"{card.get('summary', '')}")
            st.markdown("------")
            import json as _json
            st.code(_json.dumps(card, ensure_ascii=False, indent=2), language="json")
    else:
        with st.chat_message("assistant"):
            st.markdown("------")
            st.markdown("FINAL DAY (7): 마지막 전략 정리를 한 문단으로 작성해 주세요.")
            st.markdown("------")


def render_input_help(day: int):
    if 1 <= day <= 6:
        show_help = True
        if show_help:
            st.code(
                "형식 요약: 공손한 한국어, 한 문단, 구체적 선택과 근거 포함\n"
                "예시: 제품 고도화에 60%, 마케팅에 40%를 배분하겠습니다. 핵심 기능 완성을 우선하여 전환율을 높이고, 마케팅은 소규모로 가설을 검증합니다.",
                language="text",
            )
    elif day == 7:
        show_help = True
        if show_help:
            st.code("한 문단으로 일주일 전략 회고 및 다음 계획을 요약해 주세요.", language="text")


def can_advance(day: int) -> bool:
    return day in st.session_state.daily_report_by_day


# Sidebar status
with st.sidebar:
    st.markdown("------")
    st.markdown("STATUS")
    st.markdown("------")
    st.markdown(f"DAY: {st.session_state.day} / 7")
    st.markdown(f"SCORE: {st.session_state.score}")
    st.markdown("GENERATOR: mock (no engine)")
    st.markdown("SCORER:    mock (no engine)")
    st.markdown("------")


# Main flow: show event + input help
render_event_card(st.session_state.day)
render_input_help(st.session_state.day)


# Single chat input for this page
user_text = st.chat_input("C:\\> 오늘의 한 문단을 입력해 주세요 _")

if user_text:
    with st.chat_message("user"):
        st.code(f"C:\\DAY{st.session_state.day}> {user_text}", language="text")

    try:
        report = _mock_daily_report(st.session_state.day, st.session_state.score)

        st.session_state.logs.append(report)
        st.session_state.score = report.get("score", st.session_state.score)
        st.session_state.daily_report_by_day[st.session_state.day] = report
        st.session_state.last_error = None

        with st.chat_message("assistant"):
            st.markdown("------")
            st.markdown("DAILY REPORT RECEIVED (MOCK)")
            st.markdown("------")
            show_daily_json = True
            if show_daily_json:
                import json as _json
                st.code(_json.dumps(report, ensure_ascii=False, indent=2), language="json")

        if st.session_state.day == 7:
            final_report = _mock_final_report(
                day=st.session_state.day,
                score=st.session_state.score,
                logs=st.session_state.logs,
            )
            st.session_state.final_report = final_report
            show_final_json = True
            if show_final_json:
                import json as _json
                st.code(_json.dumps(final_report, ensure_ascii=False, indent=2), language="json")

    except Exception as e:
        st.session_state.last_error = f"{e}"
        with st.chat_message("assistant"):
            st.error("Mock flow failed unexpectedly. Please try again.")


# Next Day button (enabled after a daily report is present)
cols = st.columns([1, 2, 1])
with cols[1]:
    advance_disabled = not can_advance(st.session_state.day) or st.session_state.day >= 7
    if st.button("[N] Next Day", disabled=advance_disabled):
        if st.session_state.day < 7:
            st.session_state.day += 1
            st.session_state.last_error = None


if st.session_state.last_error:
    st.info(st.session_state.last_error)
