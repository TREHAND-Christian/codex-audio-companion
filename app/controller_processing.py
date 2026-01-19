from langdetect import detect

from .ui.options_data import get_target_lang_label_text


class ProcessingMixin:
    def update_last_response(self, text: str):
        if self.cfg.app_paused:
            return
        h = str(hash(text))
        if h == self.last_response_hash:
            return
        self.last_response_hash = h
        self.last_response_text = text
        try:
            self.last_detected_lang = detect(text[:1000])
        except Exception:
            self.last_detected_lang = "?"
        # Auto-detect uniquement tant qu'aucun choix manuel n'a ete fait.
        if not self.cfg.translate_enabled and getattr(self, "_auto_lang_enabled", True):
            detected = (self.last_detected_lang or "").lower()
            if detected and detected != "?":
                self.cfg.target_lang = detected
                voice_id = self.tts.pick_voice_for_lang(detected)
                if voice_id:
                    self.cfg.tts_voice_id = voice_id
        if getattr(self, "_options_dialog", None) is not None and self._options_dialog.isVisible():
            self._options_dialog.refresh_voice_list_from_context()

        if self._skip_first_auto_read:
            self._skip_first_auto_read = False
            return

        self._allow_translation_window = True

        if (
            self.cfg.auto_read_new_responses
            and not self.cfg.app_paused
            and self.cfg.tts_enabled
            and not self.cfg.tts_mute
        ):
            self.tts.stop()
            self.read_last_response()
        else:
            self._refresh_translation_only()
    def read_last_response(self):
        if self.cfg.app_paused:
            self.notify("App en pause", "Reprends l'app pour lire automatiquement.")
            self._refresh_ui()
            return

        if not self.cfg.tts_enabled:
            self._refresh_ui()
            return

        self._allow_translation_window = True

        self._process_last_response(speak=not self.cfg.tts_mute)
    def _refresh_translation_only(self):
        self._process_last_response(speak=False)
    def _process_last_response(self, speak: bool):
        text = (self.last_response_text or "").strip()
        if not text:
            self._queue_translation_update(
                "",
                get_target_lang_label_text(self.cfg.ui_lang, self.cfg.target_lang),
                False,
            )
            self._refresh_ui()
            return

        src_lang = "?"
        try:
            src_lang = detect(text[:1000])
        except Exception:
            src_lang = "?"
        self.last_detected_lang = src_lang
        # Auto-detect uniquement tant qu'aucun choix manuel n'a ete fait.
        if not self.cfg.translate_enabled and getattr(self, "_auto_lang_enabled", True):
            detected = (src_lang or "").lower()
            if detected and detected != "?":
                self.cfg.target_lang = detected
                voice_id = self.tts.pick_voice_for_lang(detected)
                if voice_id:
                    self.cfg.tts_voice_id = voice_id

        if self.cfg.translate_enabled and self.translator is None:
            try:
                from googletrans import Translator
                self.translator = Translator()
                self.tts_pipeline.translator = self.translator
            except Exception:
                self.translator = None
                self.notify("Traduction indisponible", "googletrans non charg'.")

        result = self.tts_pipeline.process(
            text=text,
            target_lang=self.cfg.target_lang.lower(),
            translate_enabled=self.cfg.translate_enabled,
            detected_lang=self.last_detected_lang,
            voice_id=self.cfg.tts_voice_id,
        )
        self.cfg.target_lang = result.effective_lang
        if result.voice_id:
            self.cfg.tts_voice_id = result.voice_id
        self.last_spoken_text = result.spoken_text
        self.last_translation_text = result.display_text
        self.last_translation_lang = self.cfg.target_lang
        self.last_translation_label = get_target_lang_label_text(self.cfg.ui_lang, self.cfg.target_lang)
        show_text = self.cfg.show_translation_window and bool(result.display_text.strip())
        # If we are about to speak (new response read), force texte above Options once.
        if speak and show_text:
            self._force_text_on_top_once = True
        self._queue_translation_update(result.display_text, self.last_translation_label, show_text)
        if speak and self._is_lang_available(self.cfg.target_lang):
            self._speak(result.spoken_text)
    def _queue_translation_update(self, text: str, label: str, show: bool):
        self.translationUpdateRequested.emit(text, label, show and self._allow_translation_window)
    def _apply_translation_update(self, text: str, label: str, show: bool):
        if show and (text or '').strip():
            self.translation_window.set_translation(text, label)
            if not self.translation_window.isVisible():
                self.translation_window.show()
            # Only bring texte above Options when a new response is read (one-shot).
            if self._force_text_on_top_once:
                self._force_text_on_top_once = False
                self._raise_windows(force_text=True)
            else:
                # Keep minibar on top, but don't reorder texte/options.
                self._raise_windows(force_text=False)
            return
        if self.translation_window.isVisible():
            if not label:
                label = get_target_lang_label_text(self.cfg.ui_lang, self.cfg.target_lang)
            self.translation_window.set_translation('', label)
            self.translation_window.hide()
    def _is_lang_available(self, code: str) -> bool:
        code = (code or "").lower()
        available_langs = set()
        try:
            if hasattr(self.tts, "list_available_languages"):
                available_langs.update(self.tts.list_available_languages())
            else:
                for v in self.tts.list_voices():
                    for lang in (v.get("languages") or []):
                        if isinstance(lang, str) and lang.strip():
                            available_langs.add(lang.lower())
        except Exception:
            return False
        return any(l.startswith(code) for l in available_langs)
