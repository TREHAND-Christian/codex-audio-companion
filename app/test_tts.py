from app.memory_store import MemoryStore
from app.tts.tts_manager import TTSManager

def main():
    cfg = MemoryStore().load()
    tts = TTSManager()

    print("=== test_tts ===")
    print("voice_id:", getattr(cfg, "tts_voice_id", ""))
    print("volume:", getattr(cfg, "tts_volume", ""))
    print("rate:", getattr(cfg, "tts_rate", ""))

    voices = tts.list_voices() or []
    print("Voix:", [v.get("id") for v in voices])

    if getattr(cfg, "tts_mute", False):
        print("SKIP: cfg.tts_mute=True")
        return

    tts.speak("Test CodexTTS. Lecture de vérification.", cfg)
    print("OK (si tu as entendu la voix)")

if __name__ == "__main__":
    main()
