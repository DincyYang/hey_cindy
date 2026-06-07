# command_listener.py
import re
import time
import sounddevice as sd
import numpy as np
import speech_recognition as sr


_QUIT_PAT = re.compile(r"\b(quit|exit|stop|goodbye|bye)\b", re.I)
_ON_PAT = re.compile(r"\b(on|turn\s+on|lights?\s+on|lamp\s+on)\b", re.I)
_OFF_PAT = re.compile(r"\b(off|turn\s+off|lights?\s+off|lamp\s+off)\b", re.I)


def _record_audio(duration_s: float, sample_rate: int) -> bytes:
    """Record mono float32 audio and return PCM16 bytes."""
    audio = sd.rec(
        int(duration_s * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32"
    )
    sd.wait()

    pcm = (audio[:, 0] * 32767).astype(np.int16)
    return pcm.tobytes()


def _recognize_google(audio_bytes: bytes, sample_rate: int) -> str:
    recognizer = sr.Recognizer()
    audio_data = sr.AudioData(audio_bytes, sample_rate, 2)
    try:
        text = recognizer.recognize_google(audio_data, language="zh-CN")
    except sr.UnknownValueError:
        text = recognizer.recognize_google(audio_data, language="en-US")
    return text.lower().strip()


def listen_for_command(timeout=3, sample_rate=16000, retries=1, pre_silence=0.15):
    """
    Record audio and return recognized raw text (lowercased).
    Returns: raw_text (str) or None
    """
    print("🎙️ Listening for command")

    if pre_silence > 0:
        time.sleep(pre_silence)

    for attempt in range(retries + 1):
        try:
            audio_bytes = _record_audio(timeout, sample_rate)
            text = _recognize_google(audio_bytes, sample_rate)
            print(f"🧠 Heard: {text}")
            return text  # ✅ 只返回文本，不做解析，不发云端

        except sr.UnknownValueError:
            print("⚠️ Could not understand audio")
            if attempt < retries:
                print("🔁 Retrying...")
                continue
            return None

        except sr.RequestError as e:
            print(f"⚠️ Speech recognition error: {e}")
            return None