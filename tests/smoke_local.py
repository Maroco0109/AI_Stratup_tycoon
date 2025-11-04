"""
Local Ollama reachability smoke test (qualitative only)

Purpose
- Verify Ollama responds and returns a JSON block containing day, reason, llm_summary
  for a Day 2 obstacle description.

Run
  python -m tests.smoke_local
"""

import json
import re
import sys
from typing import Any, Dict

import requests

from config import OLLAMA_BASE_URL, MODEL_NAME


def extract_json_block(text: str) -> Dict[str, Any]:
    """Parse the first JSON object inside a ```json fenced block."""
    fence = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if not fence:
        raise ValueError("No JSON code fence found")
    return json.loads(fence.group(1))


def main() -> int:
    # SYSTEM: JSON-only rule; USER: Day 2 obstacle, ask for qualitative output only
    messages = [
        {
            "role": "system",
            "content": (
                "Output exactly one JSON object in a ```json fenced block. "
                "Include keys: day, reason, llm_summary."
            ),
        },
        {
            "role": "user",
            "content": (
                "Day 2 obstacle: Cloud inference costs are spiking. "
                "My plan: switch to smaller context windows, add caching, and batch requests. "
                "Summarize and explain qualitatively; return JSON only."
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

