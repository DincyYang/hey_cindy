# command_listener.py
import os
import time
import sounddevice as sd
import numpy as np
import speech_recognition as sr

# Primary STT language. English first by default: the Chinese recognizer tends to
# "succeed" with a wrong homophone (e.g. "light off" -> "white of") instead of
# raising, which starved the English fallback. Override with HEY_CINDY_STT_LANG.
PRIMARY_LANG = os.environ.get("HEY_CINDY_STT_LANG", "en-US")


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
    # Try the primary language first, then the other as a fallback.
    langs = [PRIMARY_LANG] + [l for l in ("en-US", "zh-CN") if l != PRIMARY_LANG]
    last_err = sr.UnknownValueError()
    for lang in langs:
        try:
            return recognizer.recognize_google(audio_data, language=lang).lower().strip()
        except sr.UnknownValueError as e:
            last_err = e
    raise last_err


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