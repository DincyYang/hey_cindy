# cloud_client.py
import os
import requests
from typing import Any, Dict, Optional

CLOUD_BASE = os.environ.get("HEY_CINDY_CLOUD", "http://3.234.157.34:8000").rstrip("/")
TOKEN = os.environ.get("HEY_CINDY_TOKEN", "cindy-dev-token-123")

DEFAULT_TIMEOUT_S = 5


def send_command(
    command: str,
    raw_text: Optional[str] = None,
    confidence: Optional[float] = None,
    reason: Optional[str] = None,
    source: str = "voice",
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """
    Send a normalized command to the cloud service.
    Returns a dict with either {"ok": True, ...} or {"ok": False, "error": "...", ...}.
    """
    url = f"{CLOUD_BASE}/command"

    payload = {
        "command": command,
        "raw_text": raw_text,
        "confidence": confidence,
        "reason": reason,
        "source": source,
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=timeout_s)

        # If server returns non-2xx, surface details
        if not r.ok:
            # Try to parse JSON error body, else fall back to text
            try:
                body = r.json()
            except Exception:
                body = {"detail": r.text}

            return {
                "ok": False,
                "status_code": r.status_code,
                "error": "http_error",
                "response": body,
                "url": url,
                "payload": payload,
            }

        # Success: parse JSON if possible
        try:
            data = r.json()
        except Exception:
            data = {"detail": r.text}

        return {
            "ok": True,
            "status_code": r.status_code,
            "data": data,
        }

    except requests.Timeout:
        return {
            "ok": False,
            "error": "timeout",
            "url": url,
            "payload": payload,
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "error": "request_exception",
            "message": str(e),
            "url": url,
            "payload": payload,
        }