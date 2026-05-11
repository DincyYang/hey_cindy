# normalizer.py
import os
from dataclasses import dataclass
from typing import Optional
import anthropic

@dataclass(frozen=True)
class NormalizedResult:
    normalized: str     # "on" | "off" | "unknown"
    confidence: float
    reason: str
    cleaned_text: str


def normalize_command(raw_text: Optional[str]) -> NormalizedResult:
    if not raw_text or not raw_text.strip():
        return NormalizedResult("unknown", 0.0, "empty_input", "")

    cleaned = raw_text.lower().strip()

    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": f"""You are a smart home assistant. The user just gave a voice command.
Your job is to classify the command into one of three categories:
- "on": user wants to turn the light ON
- "off": user wants to turn the light OFF  
- "unknown": command is unclear, unrelated, or contradictory

User said: "{raw_text}"

Reply with ONLY a JSON object in this exact format, nothing else:
{{"command": "on", "confidence": 0.95, "reason": "user explicitly asked to turn light on"}}"""
            }
        ]
    )

    import json
    try:
        result = json.loads(message.content[0].text)
        return NormalizedResult(
            normalized=result.get("command", "unknown"),
            confidence=result.get("confidence", 0.0),
            reason=result.get("reason", "llm_classification"),
            cleaned_text=cleaned,
        )
    except Exception:
        return NormalizedResult("unknown", 0.0, "llm_parse_error", cleaned)

