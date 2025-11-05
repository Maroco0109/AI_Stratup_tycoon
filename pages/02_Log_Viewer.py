"""
Streamlit 로그 뷰어

기능
- logs/interactions.jsonl 파일의 JSON Lines 레코드를 읽어옵니다.
- page/kind/day로 필터링하고, 최근 N개의 레코드만 표시합니다.
- 테이블 요약과 각 레코드의 원본 JSON을 함께 제공합니다.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import streamlit as st

from log import DEFAULT_LOG_DIR, DEFAULT_LOG_FILE  # type: ignore


st.set_page_config(page_title="AI Startup Tycoon — Logs", page_icon="🗒️", layout="wide")

st.title("Logs — interactions.jsonl")


def load_logs(path: str) -> List[Dict[str, Any]]:
    """JSONL 로그 파일을 읽어 파싱된 레코드 리스트로 반환합니다."""
    records: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return records
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    # Skip malformed lines
                    continue
    except Exception:
        pass
    return records


def flatten_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """UI 테이블에 맞게 레코드를 평탄화(핵심 필드만 추출)합니다."""
    row: Dict[str, Any] = {
        "ts": rec.get("ts"),
        "page": rec.get("page"),
        "kind": rec.get("kind"),
        "day": rec.get("day"),
        "generator": rec.get("generator"),
        "scorer": rec.get("scorer"),
    }
    if rec.get("kind") == "daily":
        rep = rec.get("report") or {}
        row["delta"] = rep.get("delta")
        row["score"] = rep.get("score")
    elif rec.get("kind") == "final":
        row["final_score"] = rec.get("score")
        fr = rec.get("final_report") or {}
        row["final_grade"] = fr.get("final_grade")
    return row


# 제어 영역(필터/개수)
log_path = os.path.join(DEFAULT_LOG_DIR, DEFAULT_LOG_FILE)
st.caption(f"Source: {log_path}")

records = load_logs(log_path)

pages = sorted({r.get("page", "") for r in records})
kinds = sorted({r.get("kind", "") for r in records})
days = sorted({int(r.get("day", 0)) for r in records if isinstance(r.get("day"), (int, float))})

cols = st.columns(4)
with cols[0]:
    last_n = st.number_input("Last N records", min_value=10, max_value=5000, value=200, step=10)
with cols[1]:
    page_filter = st.selectbox("Filter by page", options=["(all)"] + pages, index=0)
with cols[2]:
    kind_filter = st.selectbox("Filter by kind", options=["(all)"] + kinds, index=0)
with cols[3]:
    day_filter = st.selectbox("Filter by day", options=["(all)"] + [str(d) for d in days], index=0)


# 필터 적용
def match_filters(rec: Dict[str, Any]) -> bool:
    if page_filter != "(all)" and rec.get("page") != page_filter:
        return False
    if kind_filter != "(all)" and rec.get("kind") != kind_filter:
        return False
    if day_filter != "(all)" and str(rec.get("day")) != day_filter:
        return False
    return True


filtered = [r for r in records if match_filters(r)]
filtered = filtered[-int(last_n):] if filtered else []

st.markdown(f"Showing {len(filtered)} record(s)")

# 표 형태 요약
rows = [flatten_record(r) for r in filtered]
if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No logs yet. Interact with the app to generate logs.")

# 원본 JSON 블록
with st.expander("Raw JSON records"):
    for r in filtered:
        st.code(json.dumps(r, ensure_ascii=False, indent=2), language="json")

# 다운로드 버튼(로그 파일이 존재하는 경우에만 노출)
if os.path.exists(log_path):
    try:
        with open(log_path, "rb") as f:
            st.download_button("Download interactions.jsonl", data=f, file_name="interactions.jsonl", mime="application/jsonl")
    except Exception:
        pass
