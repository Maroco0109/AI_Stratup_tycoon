"""
Relaxed issuer prompt builders for OpenAI path.

Keeps JSON-fence rules while allowing freer, less rigid events.
"""

from __future__ import annotations

from prompts.templates import input_guidelines  # type: ignore


def _issuer_system_prompt_relaxed(day: int, mode: str) -> str:
    """Lighter issuer system prompt: preserves JSON fence, frees content."""
    guideline = input_guidelines(day) or ""
    base = (
        "Follow only these minimal rules.\n"
        "- Output exactly one JSON object inside a single ```json fenced block.\n"
        "- No extra text/emojis/comments/repetition outside the fence.\n"
        "- Header keys: role=\\\"OpenAI\\\", day.\n"
        "- Use Korean polite tone inside JSON string values.\n"
        "- (Optional) Inspiration guideline:\n"
        f"{guideline}\n"
    )
    if mode == "event":
        return base + (
            "Schema: type=\\\"event_card\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
            "- Offer an incident, challenge, or opportunity relevant to AI startups\n"
            "- Keep summary concise (1-2 sentences). Numbers/metrics are optional.\n"
            "- eval_focus can be 1-2 short topics; format is flexible.\n"
            "- response_instructions: one friendly sentence inviting a one-paragraph reply.\n"
            "- Do not include answers/analysis; output only the card JSON.\n"
        )
    return base + (
        "Schema: type=\\\"daily_qual\\\", day, reason, llm_summary.\n"
        "- 1-2 sentences each, natural prose. No lists/line breaks.\n"
        "- No scores, grades, or numeric deltas.\n"
    )


def _issuer_event_payload_relaxed(day: int) -> str:
    """Minimal payload to elicit a freer event card while keeping schema."""
    return (
        "Please produce an event_card(JSON) for the given day.\n"
        f"- Day: {day}\n"
        "- Be creative: challenge, or opportunity are all fine; Metrics optional.\n"
        "- Required keys: type=\\\"event_card\\\", role=\\\"EEVE\\\", day, title, summary, constraints[], eval_focus[], response_instructions.\n"
        "- Output exactly one JSON object inside a single ```json fenced block."
    )

