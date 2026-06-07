# wake_word.py
import sounddevice as sd
import numpy as np
import pvporcupine
import time
import threading


class WakeWordDetector:
    def __init__(self, access_key, keyword_path, device_index=None):
        self.porcupine = pvporcupine.create(
            access_key=access_key,
            keyword_paths=[keyword_path]
        )
        self.device_index = device_index
        self.last_trigger_time = 0

        self.wake_event = threading.Event()
        self.pause_event = threading.Event()  # 新增：暂停监听

    def listen(self):
        print("🎤 Listening for wake word...")

        def audio_callback(indata, frames, time_info, status):
            if self.pause_event.is_set():
                return  # 🔴 让出麦克风

            pcm = (indata[:, 0] * 32767).astype(np.int16)
            if len(pcm) != self.porcupine.frame_length:
                return

            if self.porcupine.process(pcm) >= 0:
                now = time.time()
                if now - self.last_trigger_time > 1.0:
                    self.last_trigger_time = now
                    self.wake_event.set()

        with sd.InputStream(
            device=self.device_index,
            channels=1,
            samplerate=self.porcupine.sample_rate,
            blocksize=self.porcupine.frame_length,
            dtype="float32",
            callback=audio_callback
        ):
            while True:
                time.sleep(0.05)
