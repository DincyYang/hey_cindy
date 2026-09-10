# command.py
import logging
from typing import Optional

import pyttsx3

from local.cloud_client import send_command
from local.normalizer import NormalizedResult

logger = logging.getLogger(__name__)


def speak(text: str):
    engine = pyttsx3.init()
    engine.setProperty("rate", 180)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def execute(
    command: str,
    result: Optional[NormalizedResult] = None,
    *,
    source: str = "voice",
    pipeline_ms: Optional[float] = None,
) -> bool:
    """Act on a decided command.

    `result` carries the classification plus its instrumentation; forwarding it
    is what gives the cloud (and the dashboard) per-command latency, token usage
    and cost instead of a bare on/off. `pipeline_ms` overrides the classifier's
    own timing with the end-to-end pipeline latency when the caller measured it.
    """
    cmd = command.lower().strip()

    if cmd in ("quit", "exit", "stop", "bye", "goodbye"):
        speak("Goodbye. See you next time.")
        print("👋 Exiting program")
        return False

    if cmd in ("on", "off"):
        latency = pipeline_ms if pipeline_ms is not None else getattr(result, "latency_ms", None)
        try:
            resp = send_command(
                cmd,
                raw_text=getattr(result, "cleaned_text", None),
                confidence=getattr(result, "confidence", None),
                reason=getattr(result, "reason", None),
                source=source,
                latency_ms=round(latency, 2) if latency is not None else None,
                input_tokens=getattr(result, "input_tokens", None),
                output_tokens=getattr(result, "output_tokens", None),
            )
            print("☁️ Cloud execute:", resp)
            speak(f"Light turned {cmd}")
        except Exception as e:
            print("☁️ Cloud execute failed:", e)
            logger.error("Cloud execute failed (%s)", e)
            speak("Cloud error")
        return True

    speak("I did not understand")
    print("⚠️ Unknown command:", cmd)
    return True
