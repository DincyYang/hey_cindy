# command.py
import pyttsx3
from local.cloud_client import send_command

def speak(text: str):
    engine = pyttsx3.init()
    engine.setProperty("rate", 180)
    engine.say(text)
    engine.runAndWait()
    engine.stop()

def execute(command: str) -> bool:
    cmd = command.lower().strip()

    if cmd in ("quit", "exit", "stop", "bye", "goodbye"):
        speak("Goodbye. See you next time.")
        print("👋 Exiting program")
        return False

    if cmd in ("on", "off"):
        try:
            resp = send_command(cmd)   # 改成发云端
            print("☁️ Cloud execute:", resp)
            speak(f"Light turned {cmd}")
        except Exception as e:
            print("☁️ Cloud execute failed:", e)
            speak("Cloud error")
        return True

    speak("I did not understand")
    print("⚠️ Unknown command:", cmd)
    return True