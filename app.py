"""
Streamlit 메인 UI

목표
- 로컬 전용 LLM 게임(7일 루프)의 단일 페이지 채팅 UI 제공
- Streamlit의 st.chat_message / st.chat_input 제약을 준수(메인 영역에 chat_input 1개)
- 엔진(engine.py)에서 산출하는 일일/최종 리포트를 JSON 카드로 표시

구성 요약
- 사이드바: 현재 일자(1~7), 현재 점수
- 메인: 이벤트 카드 → 입력 가이드(형식/예시) → 사용자 입력(chat_input) → 일일 리포트 JSON → Next Day 버튼

주요 포인트
- chat_input은 페이지당 1개만 배치(중복 생성 금지)
- 엔진 응답(JSON) 파싱 실패 시 사용자 친화적 오류 표시, 일자(day)는 유지
- Day 7에서 judge 이후 최종 리포트 표시
"""

import streamlit as st

# External engine and config imports (stubs until engine.py/config.py exist)
from engine import get_event_card, judge_day, get_final_report  # type: ignore
from config import (
    OLLAMA_BASE_URL,
    MODEL_NAME,
    OPENAI_MODEL,
    OPENAI_BASE_URL,
)  # type: ignore
from prompts.templates import input_guidelines, input_example  # type: ignore


# Title and initial session setup
st.set_page_config(page_title="AI Startup Tycoon — Local", page_icon="💼")
st.title("AI Startup Tycoon — Local")


# Session state 초기화
# - day: 현재 날짜(1~7)
# - score: 현재 점수(기본 100)
# - logs: 일일 평가 결과(JSON dict)의 누적 리스트
# - *_by_day: 각 일자의 캐시(이벤트 카드, 데일리 리포트)
# - final_report: Day 7 이후 최종 리포트 캐시
# - last_error: 최근 오류 메시지(UX 피드백)
if "day" not in st.session_state:
    st.session_state.day = 1
if "score" not in st.session_state:
    st.session_state.score = 100
if "logs" not in st.session_state:
    st.session_state.logs = []  # list of per-day dicts
if "daily_report_by_day" not in st.session_state:
    st.session_state.daily_report_by_day = {}
if "event_card_by_day" not in st.session_state:
    st.session_state.event_card_by_day = {}
if "final_report" not in st.session_state:
    st.session_state.final_report = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None


# Sidebar: 현재 상태 표시(일자/점수/모델 정보)
with st.sidebar:
    st.subheader("Status")
    st.metric("Day", f"{st.session_state.day} / 7")
    st.metric("Score", st.session_state.score)
    st.caption(f"Generator: {MODEL_NAME} @ {OLLAMA_BASE_URL}")
    st.caption(f"Scorer: {OPENAI_MODEL} @ {OPENAI_BASE_URL}")


def render_event_card(day: int):
    """일자별 이벤트 카드 렌더링(1~6일차).

    - 엔진에서 결정론적 event_card를 받아와 표시
    - Day 7은 최종 정리 안내 문구만 출력
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
            st.markdown(f"**Day {day} Event**: {card.get('title', 'N/A')}")
            if card.get("summary"):
                st.write(card["summary"])
            with st.expander("Event JSON", expanded=False):
                st.json(card)
    else:
        with st.chat_message("assistant"):
            st.markdown("**Final Day (7)**: Share your final strategy wrap-up.")


def render_input_help(day: int):
    """README 기준(스코어 반영 Criterion)에 맞춘 입력 형식/예시 표시.

    - 형식: 해당 일자에서 요구되는 한 문단 구성 요소 요약
    - 예시: 한 문단 예시 텍스트(사용자에게 방향성 제공)
    """
    if 1 <= day <= 6:
        with st.expander("입력 형식 안내 (예시 포함)", expanded=False):
            st.markdown(f"**형식 요약**: {input_guidelines(day)}")
            example = input_example(day)
            if example:
                st.markdown("**예시(한 문단)**")
                st.write(example)
    elif day == 7:
        with st.expander("입력 형식 안내", expanded=False):
            st.write("한 문단으로 이번 주의 전략과 성과 요약, 리스크·다음 단계 제시.")


def can_advance(day: int) -> bool:
    return day in st.session_state.daily_report_by_day


# 메인 데일리 플로우
# 1) 이벤트 카드 요청/표시(Day 1~6). Day 7은 최종 답안 준비.
render_event_card(st.session_state.day)
render_input_help(st.session_state.day)


# 2) 사용자 입력(chat_input)
#    - Streamlit 제약: 메인 영역에 chat_input은 1개만 허용
#    - 한 문단 입력을 유도(README 형식 안내 참고)
user_text = st.chat_input("Your one-paragraph response for today…")

if user_text:
    # 3) 입력 제출 시, 엔진 judge 호출 → 일일 리포트 수신
    with st.chat_message("user"):
        st.write(user_text)

    try:
        report = judge_day(st.session_state.day, user_text, st.session_state.score)
        # Basic schema check; engine should ensure shape, but we keep it safe here.
        if not isinstance(report, dict) or (
            st.session_state.day <= 6 and not all(k in report for k in ["day", "delta", "score", "reason", "llm_summary"])  # noqa: E501
        ):
            raise ValueError("Engine returned malformed JSON for daily report.")

        # 4) 로그 누적, 점수 업데이트, JSON 결과 카드 표시
        st.session_state.logs.append(report)
        st.session_state.score = report.get("score", st.session_state.score)
        st.session_state.daily_report_by_day[st.session_state.day] = report
        st.session_state.last_error = None

        with st.chat_message("assistant"):
            st.markdown("Daily report received.")
            with st.expander("Daily JSON (report)", expanded=True):
                st.json(report)

        # 5) Day 7인 경우, judge 이후 최종 리포트 계산/표시
        if st.session_state.day == 7:
            try:
                final_report = get_final_report(
                    day=st.session_state.day,
                    score=st.session_state.score,
                    logs=st.session_state.logs,
                )
                st.session_state.final_report = final_report
                with st.expander("Final Report", expanded=True):
                    st.json(final_report)
            except Exception as e:
                st.session_state.last_error = f"Failed to compute final report: {e}"

    except Exception as e:
        # 오류 처리: 일자는 유지, 사용자에게 친화적 메시지 표시
        st.session_state.last_error = f"{e}"
        with st.chat_message("assistant"):
            st.error("Malformed or failed engine response. Please try again.")


# Next Day 버튼: 현재 일자의 리포트가 존재할 때만 활성화
cols = st.columns([1, 2, 1])
with cols[1]:
    advance_disabled = not can_advance(st.session_state.day) or st.session_state.day >= 7
    if st.button("Next Day", disabled=advance_disabled):
        if st.session_state.day < 7:
            st.session_state.day += 1
            # Clear any error and continue; next event card will load lazily.
            st.session_state.last_error = None


# Display any sticky errors
if st.session_state.last_error:
    st.info(st.session_state.last_error)


# 확장 포인트(가이드)
# - 평가/스코어링 로직은 engine.py에서 관리하고, UI는 결과만 표시합니다.
# - st.session_state.logs를 CSV로 저장하는 ‘내보내기’ 버튼을 추가할 수 있습니다.
# - chat_input은 1개 유지(멀티 입력 필드 사용 시 Streamlit 제약 위반 가능).
