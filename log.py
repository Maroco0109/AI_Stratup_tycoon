"""
사용자-모델 상호작용을 기록하는 간단한 JSON 로깅 유틸리티.

기능
- logs/interactions.jsonl 파일에 JSON Lines 형식으로 한 줄당 한 레코드를 기록합니다.
- 일일 상호작용(daily)과 최종 보고(final) 모두를 위한 헬퍼를 제공합니다.
- 로깅 실패는 UI 동작을 방해하지 않도록 조용히 무시합니다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


DEFAULT_LOG_DIR = "logs"          # 로그 디렉터리 기본 경로
DEFAULT_LOG_FILE = "interactions.jsonl"  # JSONL 파일명


def _ensure_dir(path: str) -> None:
    """디렉터리가 없으면 생성합니다(존재해도 안전)."""
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        # If making the directory fails, we silently ignore to avoid breaking the app
        pass


def _now_iso() -> str:
    """UTC 기준 ISO8601 타임스탬프 문자열을 반환합니다."""
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(record: Dict[str, Any], dir_path: str = DEFAULT_LOG_DIR, filename: str = DEFAULT_LOG_FILE) -> str:
    """레코드를 JSON Lines 형식으로 파일 끝에 추가합니다."""
    _ensure_dir(dir_path)
    path = os.path.join(dir_path, filename)
    try:
        with open(path, "a", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
            f.write("\n")
    except Exception:
        # Swallow logging errors; logging should never crash the UI
        pass
    return path


def clear_logs(dir_path: str = DEFAULT_LOG_DIR, filename: str = DEFAULT_LOG_FILE) -> bool:
    """Delete the JSONL log file to initialize logs for a new session.

    Returns True if the file was removed or didn’t exist; False if an unexpected
    error occurred. This is safe to call multiple times.
    """
    _ensure_dir(dir_path)
    path = os.path.join(dir_path, filename)
    try:
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False


def log_daily(page: str, day: int, user_text: str, report: Dict[str, Any], generator: str, scorer: str) -> str:
    """일일 상호작용(입력/리포트)을 로그로 남깁니다."""
    record: Dict[str, Any] = {
        "ts": _now_iso(),
        "page": page,
        "kind": "daily",
        "day": int(day),
        "generator": str(generator),
        "scorer": str(scorer),
        "user_text": user_text,
        "report": report,
    }
    return _append_jsonl(record)


def log_final(page: str, score: int, final_report: Dict[str, Any], generator: str, scorer: str) -> str:
    """최종 보고(7일차) 기록을 남깁니다."""
    record: Dict[str, Any] = {
        "ts": _now_iso(),
        "page": page,
        "kind": "final",
        "day": 7,
        "generator": str(generator),
        "scorer": str(scorer),
        "score": int(score),
        "final_report": final_report,
    }
    return _append_jsonl(record)
