"""
Streamlit 세션 상태 초기화 유틸리티

공유 키
- day: 현재 진행 일차(1~7)
- score: 누적 점수(0 이상)
- logs: 일일 요약 JSON을 순차적으로 적재하는 리스트
- daily_report_by_day: 일차별 리포트 캐시(dict)
- event_card_by_day: 일차별 이벤트 카드 캐시(dict)
- final_report: 7일차 최종 보고서(dict 또는 None)
- last_error: 최근 오류 메시지(str 또는 None)
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st


def init_session_state() -> None:
    """세션 상태를 최초 1회 안전하게 초기화합니다."""
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
