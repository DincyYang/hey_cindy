# normalizer.py
"""Turn a raw voice transcript into a structured light-command intent.

Primary path: Claude classifies the command. If the API key is missing or the
call fails/times out, we fall back to a simple offline keyword matcher so the
voice assistant still does something reasonable instead of crashing.
"""
import os
import json
import logging
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# Migrated from claude-sonnet-4-5. For this binary classification a cheaper
# model (claude-haiku-4-5) would also work — override via HEY_CINDY_MODEL.
MODEL = os.environ.get("HEY_CINDY_MODEL", "claude-sonnet-4-6")
LLM_TIMEOUT_S = float(os.environ.get("HEY_CINDY_LLM_TIMEOUT", "5"))

VALID_COMMANDS = ("on", "off", "unknown")
# Machine-readable reason codes that drive the decision layer (see decision.py).
VALID_CATEGORIES = ("clear", "conflict", "negated", "unrelated", "ambiguous", "error")


@dataclass(frozen=True)
class NormalizedResult:
    normalized: str       # "on" | "off" | "unknown"
    confidence: float
    category: str         # one of VALID_CATEGORIES
    reason: str           # human-readable explanation
    cleaned_text: str


_PROMPT = """You are the intent classifier for a smart-home light assistant.
Classify the user's voice command (English or Chinese).

Return ONLY a JSON object, no other text, with these fields:
- "command": "on" if the user wants the light ON, "off" if OFF, "unknown" otherwise
- "confidence": a number from 0.0 to 1.0
- "category": one of
    "clear"     - an unambiguous on/off request (e.g. "turn on the light", "把灯打开")
    "conflict"  - the user asked for both on and off
    "negated"   - the user explicitly does NOT want the action (e.g. "don't turn on the light")
    "unrelated" - not about the light at all
    "ambiguous" - about the light but unclear which action
- "reason": a short human-readable explanation

User said: "{raw_text}"

Example: {{"command": "on", "confidence": 0.95, "category": "clear", "reason": "user asked to turn the light on"}}"""


def _extract_json(text: str) -> str:
    """Strip markdown code fences the model may wrap the JSON in."""
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                return part
    return text


def _keyword_fallback(cleaned: str) -> NormalizedResult:
    """Offline degraded path used when the LLM is unavailable."""
    words = set(cleaned.replace("'", " ").split())
    has_on = "on" in words or any(k in cleaned for k in ("turn on", "打开", "开灯"))
    has_off = "off" in words or any(k in cleaned for k in ("turn off", "关掉", "关灯", "关闭"))
    negated = any(k in cleaned for k in ("don't", "do not", "not ", "别", "不要"))

    if has_on and has_off:
        return NormalizedResult("unknown", 0.4, "conflict", "keyword: both on and off", cleaned)
    if negated and (has_on or has_off):
        return NormalizedResult("unknown", 0.4, "negated", "keyword: negated command", cleaned)
    if has_on:
        return NormalizedResult("on", 0.6, "clear", "keyword match: on", cleaned)
    if has_off:
        return NormalizedResult("off", 0.6, "clear", "keyword match: off", cleaned)
    return NormalizedResult("unknown", 0.3, "unrelated", "keyword: no match", cleaned)


def normalize_command(raw_text: Optional[str]) -> NormalizedResult:
    if not raw_text or not raw_text.strip():
        return NormalizedResult("unknown", 0.0, "unrelated", "empty_input", "")

    cleaned = raw_text.lower().strip()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; using keyword fallback")
        return _keyword_fallback(cleaned)

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_S, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=150,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": _PROMPT.format(raw_text=raw_text)}],
        )
        data = json.loads(_extract_json(message.content[0].text.strip()))

        command = data.get("command", "unknown")
        if command not in VALID_COMMANDS:
            command = "unknown"
        category = data.get("category") or ("clear" if command in ("on", "off") else "unrelated")
        if category not in VALID_CATEGORIES:
            category = "error"

        return NormalizedResult(
            normalized=command,
            confidence=float(data.get("confidence", 0.0)),
            category=category,
            reason=data.get("reason", "llm_classification"),
            cleaned_text=cleaned,
        )
    except Exception as e:
        logger.warning("LLM classification failed (%s); using keyword fallback", e)
        return _keyword_fallback(cleaned)
