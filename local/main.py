# local/main.py — entry point. Run with: python -m local.main
import os
import sys
import time
import logging
import threading

import numpy as np
import simpleaudio as sa

from local.wake_word import WakeWordDetector
from local.command import execute, speak
from local.command_listener import listen_for_command
from local.normalizer import normalize_command
from local.decision import decide_from_result

# ========= Configuration =========
# Get a free Porcupine access key at https://console.picovoice.ai/
ACCESS_KEY = os.environ.get("PORCUPINE_ACCESS_KEY", "")
KEYWORD_PATH = os.environ.get(
    "HEY_CINDY_KEYWORD_PATH", "Hey-Cindy_en_mac_v4_0_0/Hey-Cindy_en_mac_v4_0_0.ppn"
)
DEVICE_INDEX = None  # system default mic
# ==================================

# ========= Logging =========
logging.basicConfig(
    filename="test_run.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)
# ============================

# ========= Beep =========
def play_beep():
    frequency = 800  # Hz
    duration = 0.12  # seconds (slightly shorter)
    sample_rate = 44100

    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(frequency * 2 * np.pi * t)

    audio = (tone * 32767).astype(np.int16)
    sa.play_buffer(audio, 1, 2, sample_rate).wait_done()
# ==========================


def handle_wake(detector: WakeWordDetector):
    detector.pause_event.set()

    print("🟢 Wake word detected!")
    logging.info("Wake word detected")

    play_beep()
    time.sleep(0.2)
    print("🔔 Speak now: on/off/quit")

    raw_text = listen_for_command(timeout=3)
    logging.info(f"Raw text heard: {raw_text!r}")

    if not raw_text:
        print("😶 No speech recognized")
        logging.info("No speech recognized")
        detector.pause_event.clear()
        return

    # 1) 系统命令优先处理
    if raw_text.strip().lower() in ("quit", "exit", "stop"):
        print("👋 Quitting...")
        logging.info("Quit command received")
        speak("Goodbye. See you next time.")
        sys.exit(0)

    # 2) 归一化
    result = normalize_command(raw_text)

    print(f"🎧 raw_text: {raw_text}")
    print(f"🧠 normalized: {result.normalized} | conf={result.confidence} | reason={result.reason}")
    print(f"🧹 cleaned: {result.cleaned_text}")

    logging.info(
        f"Normalized: {result.normalized} conf={result.confidence} "
        f"reason={result.reason} cleaned={result.cleaned_text!r}"
    )

    # 3) 决策层
    decision = decide_from_result(result)

    print(
        f"🧭 decision: action={decision.action} "
        f"command={decision.command} reason={decision.reason}"
    )
    logging.info(
        f"Decision: action={decision.action} "
        f"command={decision.command} reason={decision.reason}"
    )

    # 4) 根据决策执行
    if decision.action == "execute":
        print(f"👉 Executing: {decision.command}")
        should_continue = execute(decision.command)

        if should_continue is False:
            sys.exit(0)

    elif decision.action == "clarify":
        print(f"❓ Clarification needed: {decision.message}")
        logging.warning(
            f"Clarify command: raw={raw_text!r} cleaned={result.cleaned_text!r} "
            f"reason={result.reason}"
        )
        speak(decision.message)

        # Follow-up: listen once for the answer — no need to say the wake word again.
        followup = listen_for_command(timeout=3)
        if followup:
            fu = decide_from_result(normalize_command(followup))
            if fu.action == "execute":
                print(f"👉 Executing: {fu.command}")
                execute(fu.command)
            else:
                speak("Okay, never mind.")
        else:
            speak("Okay, never mind.")

    elif decision.action == "reject":
        print(f"⛔ Rejected: {decision.message}")
        logging.warning(
            f"Rejected command: raw={raw_text!r} cleaned={result.cleaned_text!r} "
            f"reason={result.reason}"
        )
        speak(decision.message)

    else:
        print("⚠️ No action taken.")
        logging.warning(
            f"Ignored command: raw={raw_text!r} cleaned={result.cleaned_text!r} "
            f"reason={result.reason}"
        )

    # 5) 恢复 wake word 监听
    detector.pause_event.clear()

def main():
    print("Voice to light with wake word started")
    logging.info("Program started")

    if not ACCESS_KEY:
        print("❌ PORCUPINE_ACCESS_KEY is not set. "
              "Get a free key at https://console.picovoice.ai/ and export it.")
        sys.exit(1)

    detector = WakeWordDetector(
        access_key=ACCESS_KEY,
        keyword_path=KEYWORD_PATH,
        device_index=DEVICE_INDEX
    )

    threading.Thread(target=detector.listen, daemon=True).start()

    while True:
        detector.wake_event.wait()
        detector.wake_event.clear()
        handle_wake(detector)


if __name__ == "__main__":
    import platform, sys
    logging.info(f"Python: {sys.version}")
    logging.info(f"Platform: {platform.platform()}")
    main()