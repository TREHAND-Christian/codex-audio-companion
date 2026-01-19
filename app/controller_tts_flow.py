import logging

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

logger = logging.getLogger(__name__)


class TTSFlowMixin:
    def _quit_app(self):
        try:
            self.tts.stop()
        except Exception:
            logger.exception("TTS stop failed during quit")
        self.tray.hide()
        QApplication.quit()
    def _on_play_pause(self):
        if self.tts.is_paused():
            self.tts.resume()
            self._refresh_ui()
            return
        if self.tts.is_speaking():
            self.tts.pause()
            self._refresh_ui()
            return
        self.read_last_response()
    def _on_stop(self):
        self.tts.stop()
        self._refresh_ui()
    def _restart_reading_with_new_target(self, was_speaking: bool = False):
        # L'utilisateur a choisi une langue/voix manuellement.
        self._auto_lang_enabled = False
        if not self.cfg.auto_read_new_responses:
            if self.tts.is_speaking():
                self.tts.stop()
            self._refresh_translation_only()
            return
        if self.cfg.app_paused or not self.cfg.tts_enabled or self.cfg.tts_mute:
            self._refresh_translation_only()
            return
        if was_speaking and self.tts.is_speaking():
            self.tts.stop()
        if self.tts.is_paused():
            return
        self.read_last_response()
    def _on_mute_toggle(self):
        self._set_tts_mute(not self.cfg.tts_mute)
    def _set_app_paused(self, paused: bool):
        if self.cfg.app_paused == bool(paused):
            return
        self.cfg.app_paused = bool(paused)
        if self.cfg.app_paused:
            if getattr(self, "translation_window", None) is not None:
                self.translation_window.hide()
            if getattr(self, "mini", None) is not None:
                self.mini.hide()
            if getattr(self, "_options_dialog", None) is not None:
                self._options_dialog.hide()
        self._refresh_ui()
    def _set_tts_mute(self, muted: bool):
        if self.cfg.tts_mute == bool(muted):
            return
        self.cfg.tts_mute = bool(muted)
        if self.cfg.tts_mute:
            try:
                self.tts.stop()
            except Exception:
                logger.exception("TTS stop failed while muting")
        self._refresh_ui()
    def _on_translation_window_closed(self):
        if self.translation_window.isVisible():
            self.translation_window.hide()
        if not self.cfg.show_translation_window:
            return
        self.cfg.show_translation_window = False
        self.cfg.show_translation_window_set = True
        if getattr(self, "_options_dialog", None) is not None and self._options_dialog.isVisible():
            self._options_dialog.sync_show_text_from_config()
        self._refresh_ui()
    def _apply_cfg_effects(self):
        if self.cfg.tts_mute:
            try:
                self.tts.stop()
            except Exception:
                logger.exception("TTS stop failed during config apply")
    def _speak(self, text: str):
        if self.cfg.tts_mute or not self.cfg.tts_enabled:
            return
        self.tts.speak(text, self.cfg)
        self._refresh_ui()
    def _on_tts_error(self, msg: str):
        self.notify("Erreur TTS", msg)
        self._refresh_ui()
    def notify(self, title: str, msg: str):
        try:
            self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 3000)
        except Exception:
            logger.exception("Tray notification failed")
