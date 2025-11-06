"""
로컬 Ollama 도달성 스모크 테스트(질적 출력만 확인)

목적
- Ollama가 응답하고, Day 2 장애 시나리오에 대해 ```json 코드 펜스 안의 일치하는
  JSON(daily_qual: day, reason, llm_summary)을 반환하는지 검증합니다.

실행
  python -m tests.smoke_local
"""

import json
import re
import sys
from typing import Any, Dict

import requests

from config import OLLAMA_BASE_URL, MODEL_NAME


def extract_json_block(text: str) -> Dict[str, Any]:
    """```json 코드 펜스 안의 첫 번째 JSON 객체를 괄호 균형으로 파싱합니다."""
    m = re.search(r"```json\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if not m:
        raise ValueError("No JSON code fence found")
    fenced = m.group(1).strip()

    i = 0
    n = len(fenced)
    while i < n and fenced[i] != "{":
        i += 1
    if i >= n:
        raise ValueError("No JSON object start found in fenced block")

    depth = 0
    in_str = False
    escape = False
    start = i
    for j in range(i, n):
        ch = fenced[j]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    segment = fenced[start : j + 1]
                    return json.loads(segment)
    raise ValueError("Unbalanced JSON braces in fenced block")


def main() -> int:
    # SYSTEM: JSON-only 규칙
    # USER: Day 2 장애 가정. 질적 출력만 요청.
    messages = [
        {
            "role": "system",
            "content": (
                "모든 출력은 하나의 ```json 코드 펜스 안에 JSON 객체 한 개로만 반환하세요. "
                "헤더: version=\"AST-v1\", type=\"daily_qual\", role=\"EEVE\", day. "
                "본문 키: reason, llm_summary. 한국어 공손체."
            ),
        },
        {
            "role": "user",
            "content": (
                "Day 2 obstacle: Cloud inference costs are spiking. "
                "Plan: use smaller context windows, add caching, and batch requests. "
                "Return JSON only inside a single ```json fenced block."
            ),
        },
    ]

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat"
    resp = requests.post(url, json={"model": MODEL_NAME, "messages": messages}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "message" in data:
        text = data["message"].get("content", "")
    elif isinstance(data, list):
        text = "".join(chunk.get("message", {}).get("content", "") for chunk in data)
    else:
        text = ""

    obj = extract_json_block(text)
    for k in ("day", "reason", "llm_summary"):
        assert k in obj, f"Missing key: {k}"

    print(obj)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Smoke test failed: {e}")
        sys.exit(1)
