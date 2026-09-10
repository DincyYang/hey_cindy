# normalizer.py
"""Turn a raw voice transcript into a structured light-command intent.

Primary path: Claude classifies the command. If the API key is missing or the
call fails/times out, we fall back to a simple offline keyword matcher so the
voice assistant still does something reasonable instead of crashing.

Every classification is instrumented: wall-clock latency, whether the LLM was
consulted at all, and the exact token usage the API reported. Those numbers ride
along with the result so the caller can ship them to the cloud, where they turn
into the cost/latency panel on the dashboard.
"""
import os
import json
import time
import logging
from dataclasses import dataclass, replace
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# Haiku is fast + cheap and plenty for this classification; the LLM is only
# consulted for ambiguous input anyway (see the fast path below).
MODEL = os.environ.get("HEY_CINDY_MODEL", "claude-haiku-4-5")
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
    # --- instrumentation (defaulted so existing constructor calls still work) ---
    latency_ms: float = 0.0     # wall-clock time spent classifying
    input_tokens: int = 0       # 0 when the fast path answered without the LLM
    output_tokens: int = 0
    used_llm: bool = False


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


def _usage_tokens(message) -> tuple[int, int]:
    """Pull (input, output) token counts off a Messages API response.

    Defensive: a mocked or partial response in tests has no real usage object,
    and instrumentation must never be the thing that breaks classification.
    """
    usage = getattr(message, "usage", None)
    try:
        return int(getattr(usage, "input_tokens", 0)), int(getattr(usage, "output_tokens", 0))
    except (TypeError, ValueError):
        return 0, 0


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


def _classify(raw_text: str, cleaned: str) -> NormalizedResult:
    # Fast path: an unambiguous keyword match answers instantly — no network
    # round-trip to the LLM. This is what makes "light off" feel snappy.
    kw = _keyword_fallback(cleaned)
    if kw.category == "clear":
        return kw

    # Ambiguous / unrelated input: ask the LLM for a better read, if configured.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; using keyword fallback")
        return kw

    try:
        client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_S, max_retries=1)
        message = client.messages.create(
            model=MODEL,
            max_tokens=150,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": _PROMPT.format(raw_text=raw_text)}],
        )
        in_tok, out_tok = _usage_tokens(message)
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
            input_tokens=in_tok,
            output_tokens=out_tok,
            used_llm=True,
        )
    except Exception as e:
        logger.warning("LLM classification failed (%s); using keyword fallback", e)
        return kw


def normalize_command(raw_text: Optional[str]) -> NormalizedResult:
    started = time.perf_counter()

    if not raw_text or not raw_text.strip():
        result = NormalizedResult("unknown", 0.0, "unrelated", "empty_input", "")
    else:
        cleaned = raw_text.lower().strip()
        result = _classify(raw_text, cleaned)

    result = replace(result, latency_ms=round((time.perf_counter() - started) * 1000, 2))

    # One structured line per command — the raw material for the cost/latency
    # panel and for grepping the log after a session.
    logger.info(
        "classify path=%s command=%s category=%s confidence=%.2f "
        "latency_ms=%.2f input_tokens=%d output_tokens=%d",
        "llm" if result.used_llm else "keyword",
        result.normalized, result.category, result.confidence,
        result.latency_ms, result.input_tokens, result.output_tokens,
    )
    return result
