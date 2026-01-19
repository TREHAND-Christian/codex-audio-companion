import json
from dataclasses import dataclass, field
from pathlib import Path
import os


def _storage_path() -> Path:
    root = os.environ.get("APPDATA") or os.environ.get("HOME") or "."
    return Path(root) / "SpeachCodexGPT" / "state.json"


@dataclass
class AppState:
    # Positions / tailles (px)
    mini_bar_pos_x: int = -1
    mini_bar_pos_y: int = -1
    mini_bar_draggable: bool = True
    translation_pos_x: int = -1
    translation_pos_y: int = -1
    translation_size_w: int = 100
    translation_size_h: int = 300
    options_pos_x: int = -1
    options_pos_y: int = -1

    # Options
    ui_lang: str = "fr"
    auto_read_new_responses: bool = True
    mini_bar_always_on_top: bool = True
    show_mini_bar_on_start: bool = True
    show_translation_window: bool = True
    show_translation_window_set: bool = False
    app_paused: bool = False
    tts_enabled: bool = True
    tts_mute: bool = False
    tts_voice_id: str = "winrt:Microsoft Paul"
    tts_rate: float = 1.0
    tts_volume: int = 80
    translate_enabled: bool = True
    target_lang: str = "fr"

    # Voix par langue cible
    voice_per_lang: dict = field(default_factory=lambda: {"fr": "winrt:Microsoft Paul"})


class MemoryStore:
    def __init__(self):
        self.path = _storage_path()

    def load(self) -> AppState:
        state = AppState()
        if not self.path.exists():
            return state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return state
        for key, value in raw.items():
            if hasattr(state, key):
                setattr(state, key, value)
        if not isinstance(state.voice_per_lang, dict):
            state.voice_per_lang = {"fr": "winrt:Microsoft Paul"}
        if not isinstance(state.show_translation_window_set, bool):
            state.show_translation_window_set = False
        if not state.show_translation_window_set:
            state.show_translation_window = True
        return state

    def save(self, state: AppState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            k: getattr(state, k)
            for k in state.__dataclass_fields__.keys()
        }
        self.path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
