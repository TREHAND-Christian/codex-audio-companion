import threading
import asyncio
import time
import re
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Signal, QObject


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


# WinRT TTS (voices Windows OneCore: Julie/Paul/Hortense)
try:
    from winsdk.windows.media.speechsynthesis import SpeechSynthesizer
    import winsdk.windows.media.core as media_core
    import winsdk.windows.media.playback as media_playback
except Exception:
    SpeechSynthesizer = None
    media_core = None
    media_playback = None


ALLOWED_WINRT_VOICES = set()


class TTSEvents(QObject):
    started = Signal()
    finished = Signal()
    error = Signal(str)


class TTSManager:
    """
    - WinRT (winsdk): voices "OneCore" (Julie/Paul/Hortense)
    """
    def __init__(self, cfg=None, store=None):
        self.cfg = cfg
        self.store = store
        self._pause_flag = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        self._winrt_player: Optional[object] = None
        self.events = TTSEvents()
        self._queue: List[str] = []
        self._queue_index: int = 0
        self._queue_cfg = None
        self._resume_pending = False
        self._ui_announcement = False

    def list_voices(self) -> List[Dict[str, Any]]:
        voices: List[Dict[str, Any]] = []

        if SpeechSynthesizer is not None:
            try:
                for v in SpeechSynthesizer.all_voices:
                    display = getattr(v, "display_name", "") or ""
                    lang = getattr(v, "language", "") or ""
                    if display:
                        voices.append({
                            "engine": "winrt",
                            "id": f"winrt:{display}",
                            "name": f"{display} (WinRT)",
                            "languages": [lang] if lang else [],
                        })
            except Exception:
                pass

        return voices

    def list_available_languages(self) -> List[str]:
        langs: List[str] = []
        if SpeechSynthesizer is None:
            return langs
        try:
            for v in SpeechSynthesizer.all_voices:
                lang = getattr(v, "language", "") or ""
                if lang:
                    langs.append(lang.lower())
        except Exception:
            pass
        return sorted(set(langs))

    def _winrt_voice_names(self) -> List[str]:
        names: List[str] = []
        if SpeechSynthesizer is None:
            return names
        try:
            for v in SpeechSynthesizer.all_voices:
                display = getattr(v, "display_name", "") or ""
                if display:
                    names.append(display)
        except Exception:
            pass
        return names

    def is_speaking(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    
    def pause(self) -> None:
        """Met en pause la lecture en cours (reprend au début de la phrase)."""
        with self._lock:
            self._pause_flag = True
            self._stop_flag = True
            player = self._winrt_player
        if player is not None:
            try:
                player.pause()
            except Exception:
                pass
            try:
                player.source = None
            except Exception:
                pass

    def resume(self) -> None:
        """Reprend la lecture en pause (début de la phrase courante)."""
        t = self._thread
        if t is not None and t.is_alive():
            with self._lock:
                self._resume_pending = True
            return
        with self._lock:
            if not self._pause_flag:
                return
            self._pause_flag = False
        if self._queue:
            self._start_queue(self._queue_cfg)

    def apply_live_cfg(self, cfg) -> bool:
        if cfg is None:
            return False
        if not (self.is_speaking() or self.is_paused()):
            return False
        self.pause()
        for _ in range(50):
            if not self.is_speaking():
                break
            time.sleep(0.02)
        with self._lock:
            self._queue_cfg = cfg
        self.resume()
        return True

    def is_paused(self) -> bool:
        with self._lock:
            return bool(getattr(self, "_pause_flag", False))
    def is_ui_announcement(self) -> bool:
        with self._lock:
            return bool(getattr(self, "_ui_announcement", False))
    def stop(self) -> None:
        # note: on sort le player du lock pour éviter les blocages
        with self._lock:
            self._stop_flag = True
            self._pause_flag = False
            self._resume_pending = False
            self._ui_announcement = False
            player = self._winrt_player
            self._queue = []
            self._queue_index = 0

        if player is not None:
            try:
                player.pause()
            except Exception:
                pass
            try:
                # force l'arrêt réel
                player.source = None
            except Exception:
                pass

    # ---- WinRT ----
    @staticmethod
    def _escape_xml(s: str) -> str:
        return (s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&apos;"))

    @staticmethod
    def _slider_to_speaking_rate(slider: float) -> float:
        """
        Slider: 0.0 (lent) -> 1.0 (normal) -> 2.0 (rapide)

        WinRT SpeechSynthesizerOptions.SpeakingRate:
        - min recommandé: 0.5
        - normal: 1.0
        - rapide: 2.0 (raisonnable, stable)
        """
        r = max(0.0, min(2.0, float(slider)))

        # 0..1 : 0.5 -> 1.0
        if r <= 1.0:
            return 0.5 + 0.5 * r

        # 1..2 : 1.0 -> 2.0
        return 1.0 + (r - 1.0) * 1.0

    async def _winrt_speak_async(self, text: str, voice_display_name: str, cfg) -> None:
        synth = SpeechSynthesizer()
        voice_lang = "fr-FR"

        try:
            for v in SpeechSynthesizer.all_voices:
                if getattr(v, "display_name", "") == voice_display_name:
                    synth.voice = v
                    voice_lang = getattr(v, "language", "") or voice_lang
                    break
        except Exception:
            pass

        # ✅ Vitesse fiable: SpeakingRate (1.0 = normal)
        try:
            if hasattr(synth, "options") and hasattr(synth.options, "speaking_rate"):
                synth.options.speaking_rate = self._slider_to_speaking_rate(cfg.tts_rate)
        except Exception:
            pass

        # ✅ SSML sans prosody rate (évite cumul d'effets)
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{voice_lang}">'
            f'{self._escape_xml(text)}'
            '</speak>'
        )

        stream = await synth.synthesize_ssml_to_stream_async(ssml)

        player = media_playback.MediaPlayer()
        player.source = media_core.MediaSource.create_from_stream(stream, stream.content_type)
        player.volume = clamp(int(cfg.tts_volume), 0, 100) / 100.0

        with self._lock:
            self._winrt_player = player
            self._stop_flag = False

        player.play()

        # ✅ Boucle robuste multi-postes (enums variables) + timeout anti-boucle infinie
        State = media_playback.MediaPlaybackState

        ST_PLAYING = getattr(State, "PLAYING", None) or getattr(State, "Playing", None)
        ST_PAUSED  = getattr(State, "PAUSED", None)  or getattr(State, "Paused", None)
        ST_STOPPED = getattr(State, "STOPPED", None) or getattr(State, "Stopped", None)
        ST_NONE    = getattr(State, "NONE", None)    or getattr(State, "None", None)

        started = False
        t0 = time.time()

        # Timeout intelligent: base + proportionnel au texte
        # (évite tout blocage sur poste/driver qui ne remonte pas correctement l'état)
        max_sec = 15 + (len(text) * 0.08)
        max_sec = min(max_sec, 180.0)  # cap à 3 minutes

        while True:
            # stop demandé ?
            with self._lock:
                if self._stop_flag:
                    break

            # timeout sécurité
            if (time.time() - t0) > max_sec:
                break

            try:
                state = player.playback_session.playback_state
            except Exception:
                break

            if ST_PLAYING is not None and state == ST_PLAYING:
                started = True

            if started:
                # fin selon versions
                if ST_STOPPED is not None and state == ST_STOPPED:
                    break
                if ST_PAUSED is not None and state == ST_PAUSED:
                    break
                if ST_NONE is not None and state == ST_NONE:
                    break

            await asyncio.sleep(0.05)

        # cleanup : on force un arrêt propre (pause = reprise au début de phrase).
        try:
            player.pause()
        except Exception:
            pass
        try:
            player.source = None
        except Exception:
            pass

    def _winrt_speak(self, text: str, cfg) -> None:
        if SpeechSynthesizer is None or media_core is None or media_playback is None:
            self.events.error.emit("WinRT indisponible sur ce poste.")
            return

        voice_display = cfg.tts_voice_id[len("winrt:"):] if (cfg.tts_voice_id or "").startswith("winrt:") else ""

        def run():
            try:
                self.events.started.emit()
                asyncio.run(run_sequence())
            except Exception as e:
                self.events.error.emit(str(e))
            finally:
                with self._lock:
                    self._winrt_player = None
                    self._thread = None
                    self._ui_announcement = False
                    resume = self._resume_pending and bool(self._queue)
                    if resume:
                        self._resume_pending = False
                        self._pause_flag = False
                self.events.finished.emit()
                if resume:
                    self._start_queue(self._queue_cfg)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _split_text(self, text: str) -> List[str]:
        parts = re.split(r"([.!?]+|\n+)", text)
        sentences: List[str] = []
        buf = ""
        for part in parts:
            if not part:
                continue
            buf += part
            if re.fullmatch(r"[.!?]+", part) or "\n" in part:
                s = buf.strip()
                if s:
                    sentences.append(s)
                buf = ""
        if buf.strip():
            sentences.append(buf.strip())
        return sentences

    def _start_queue(self, cfg) -> None:
        if SpeechSynthesizer is None or media_core is None or media_playback is None:
            self.events.error.emit("WinRT indisponible sur ce poste.")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            self._stop_flag = False

        voice_display = cfg.tts_voice_id[len("winrt:"):] if (cfg.tts_voice_id or "").startswith("winrt:") else ""

        async def run_sequence():
            completed = True
            for i in range(self._queue_index, len(self._queue)):
                with self._lock:
                    if self._stop_flag or self._pause_flag:
                        completed = False
                        break
                    self._queue_index = i
                await self._winrt_speak_async(self._queue[i], voice_display, cfg)
                with self._lock:
                    if self._stop_flag or self._pause_flag:
                        completed = False
                        break
            with self._lock:
                if self._pause_flag:
                    self._stop_flag = False
                elif self._stop_flag:
                    self._stop_flag = False
                    self._queue = []
                    self._queue_index = 0
                elif completed:
                    self._queue = []
                    self._queue_index = 0

        def run():
            try:
                self.events.started.emit()
                asyncio.run(run_sequence())
            except Exception as e:
                self.events.error.emit(str(e))
            finally:
                with self._lock:
                    self._winrt_player = None
                    self._thread = None
                    self._ui_announcement = False
                    resume = self._resume_pending and bool(self._queue)
                    if resume:
                        self._resume_pending = False
                        self._pause_flag = False
                self.events.finished.emit()
                if resume:
                    self._start_queue(self._queue_cfg)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    # ---- Public ----
    def speak(self, text: str, cfg=None, ui_announcement: bool = False) -> None:
        if not text.strip():
            return

        cfg = cfg or self.cfg
        if cfg is None:
            self.events.error.emit("Configuration TTS manquante.")
            return

        self.stop()
        with self._lock:
            self._pause_flag = False
            self._ui_announcement = bool(ui_announcement)
            self._ui_announcement = bool(ui_announcement)

        if not (cfg.tts_voice_id or "").strip():
            cfg.tts_voice_id = self._auto_pick_voice_id(prefer_lang="fr")
        if not (cfg.tts_voice_id or "").strip():
            self.events.error.emit("Aucune voix TTS disponible sur ce poste.")
            return

        voice_id = (cfg.tts_voice_id or "").strip()

        if voice_id.startswith("winrt:"):
            if voice_id[len("winrt:"):] not in set(self._winrt_voice_names()):
                cfg.tts_voice_id = self._auto_pick_voice_id(prefer_lang="fr")
                voice_id = (cfg.tts_voice_id or "").strip()
        else:
            cfg.tts_voice_id = self._auto_pick_voice_id(prefer_lang="fr")
            voice_id = (cfg.tts_voice_id or "").strip()
        if not voice_id or not voice_id.startswith("winrt:"):
            self.events.error.emit("Voix WinRT introuvable ou indisponible.")
            return

        if voice_id.startswith("winrt:"):
            self._queue = self._split_text(text)
            self._queue_index = 0
            self._queue_cfg = cfg
            self._start_queue(cfg)

    def _auto_pick_voice_id(self, prefer_lang: str = "fr") -> str:
        voices = self.list_voices()

        for v in voices:
            if v.get("engine") == "winrt":
                langs = [str(x).lower() for x in (v.get("languages") or [])]
                if any(l.startswith(prefer_lang) for l in langs):
                    return v["id"]

        return voices[0]["id"] if voices else ""

    def pick_voice_for_lang(self, lang: str) -> str:
        lang = (lang or "").lower()
        voices = self.list_voices() or []
        voices.sort(key=lambda x: (0 if x.get("engine") == "winrt" else 1, x.get("name", "")))
        for v in voices:
            langs = [str(x).lower() for x in (v.get("languages") or [])]
            if any(l.startswith(lang) for l in langs):
                return v.get("id") or ""
        return ""
