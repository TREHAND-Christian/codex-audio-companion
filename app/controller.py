import re

from PySide6.QtCore import Qt, QObject, Signal, QEvent, QTimer
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle, QDialog

from langdetect import detect, DetectorFactory

from .memory_store import AppState, MemoryStore
from .tts import TTSManager
from .tts.tts_pipeline import TTSPipeline
from .ui import MiniBar, OptionsDialog, TranslationWindow
from .ui.options_data import get_target_lang_label_text

# googletrans optional (Python 3.13+ breaks)
try:
    from googletrans import Translator
except Exception:
    Translator = None

DetectorFactory.seed = 0



from .controller_tray import TrayMixin
from .controller_windows import WindowsMixin
from .controller_options import OptionsMixin
from .controller_tts_flow import TTSFlowMixin
from .controller_processing import ProcessingMixin

class Controller(QObject, TrayMixin, WindowsMixin, OptionsMixin, TTSFlowMixin, ProcessingMixin):
    translationUpdateRequested = Signal(str, str, bool)
    # Recoit les messages depuis le watcher (thread secondaire) via signal Qt.
    newMessageRequested = Signal(str)

    def __init__(self, cfg: AppState, store: MemoryStore):
        super().__init__()
        # Keep app running in system tray even if all windows are closed/hidden
        QApplication.setQuitOnLastWindowClosed(False)
        self.cfg = cfg
        self.store = store

        # One-shot: raise the texte window above Options only when a new response is read.
        self._force_text_on_top_once = False

        self.tts = TTSManager(self.cfg, self.store)
        self.translator = Translator() if Translator else None
        self.tts_pipeline = TTSPipeline(self.tts, self.translator)
        if self.cfg.voice_per_lang and self.cfg.target_lang in self.cfg.voice_per_lang:
            self.cfg.tts_voice_id = self.cfg.voice_per_lang.get(self.cfg.target_lang, self.cfg.tts_voice_id)

        self.last_response_text: str = ""
        self.last_response_hash: str = ""
        self.last_detected_lang: str = "?"
        self.last_spoken_text: str = ""
        self.last_translation_text: str = ""
        self.last_translation_lang: str = ""
        self.last_translation_label: str = ""
        self._skip_first_auto_read = True
        self._allow_translation_window = False
        # Stopper l'auto-detection des langues des qu'un choix manuel est fait.
        self._auto_lang_enabled = True

        self.translationUpdateRequested.connect(self._apply_translation_update)
        self.newMessageRequested.connect(self.update_last_response)

        self.tts.events.started.connect(self._refresh_ui)
        self.tts.events.finished.connect(self._refresh_ui)
        self.tts.events.error.connect(self._on_tts_error)

        self.mini = MiniBar()
        self.mini.playPauseClicked.connect(self._on_play_pause)
        self.mini.stopClicked.connect(self._on_stop)
        self.mini.muteClicked.connect(self._on_mute_toggle)
        self.mini.optionsClicked.connect(self._open_options)
        self.mini.positionChanged.connect(self._on_position_changed)

        self._build_tray()
        self._apply_window_flags()
        self.mini.set_draggable(self.cfg.mini_bar_draggable)
        self._apply_position()
        self.cfg.mini_bar_always_on_top = bool(self.cfg.show_mini_bar_on_start)

        self.translation_window = TranslationWindow()
        self.translation_window.closed.connect(self._on_translation_window_closed)
        self.translation_window.positionChanged.connect(self._on_translation_position_changed)
        self.translation_window.sizeChanged.connect(self._on_translation_size_changed)
        if self.cfg.translation_size_w > 0 and self.cfg.translation_size_h > 0:
            self.translation_window.resize(self.cfg.translation_size_w, self.cfg.translation_size_h)
        screen = QApplication.primaryScreen()
        if self.cfg.translation_pos_x >= 0 and self.cfg.translation_pos_y >= 0:
            self.translation_window.move(self.cfg.translation_pos_x, self.cfg.translation_pos_y)
        elif screen is not None:
            geo = screen.availableGeometry()
            x = int(geo.x() + 30)
            y = int(geo.y() + geo.height() - self.translation_window.height() - 100)
            self.translation_window.move(x, y)
        self.translation_window.hide()

        self._refresh_ui()

    def _refresh_ui(self):
        self._apply_cfg_effects()
        self._apply_mini_visibility()
        playing = self.tts.is_speaking()
        self.mini.set_play_icon(playing)
        self.mini.set_mute_icon(self.cfg.tts_mute)
        self.mini.set_active(self.cfg.app_paused)
        if getattr(self, "_options_dialog", None) is not None and self._options_dialog.isVisible():
            self._options_dialog.sync_mute_from_config()
            self._options_dialog.sync_app_pause_from_config()
            self._options_dialog.sync_show_text_from_config()

        # Ne pas ouvrir la fenetre texte ici; elle ne doit s'ouvrir qu'aux nouvelles reponses.
        self._apply_translation_visibility()

        self.act_mute.setChecked(self.cfg.tts_mute)
        self.act_pause_app.setText("Reprendre le service" if self.cfg.app_paused else "Mettre le service en pause")

        voice = self.cfg.tts_voice_id or "auto"
        engine = "WinRT" if voice.startswith("winrt:") else ("SAPI" if voice.startswith("sapi:") else "Auto")

        if self.cfg.app_paused:
            status = f"⏸️ Pause app • {engine}"
        else:
            if playing:
                status = f"🔊 Lecture… ({self.last_detected_lang} → {self.cfg.target_lang}) • {engine}"
            else:
                status = f"🟢 Actif • Dernière langue: {self.last_detected_lang} • {engine}"
        if playing:
            status = f"🔊 Lecture… ({self.last_detected_lang} → {self.cfg.target_lang}) • {engine}"

        if self.cfg.tts_mute:
            status += " • 🔇 Muet"
        if self.translator is None:
            status += " • 🌐 Traduction OFF"

        self.mini.set_status(status)

        self._update_tray_icon()
        self.store.save(self.cfg)
        self._raise_windows()

    def _apply_mini_visibility(self):
        if getattr(self, "_ui_hidden", False):
            return
        if self.cfg.app_paused:
            if self.mini.isVisible():
                self.mini.hide()
            return
        should_show = bool(self.cfg.mini_bar_always_on_top)
        if should_show and not self.mini.isVisible():
            self.mini.show()
        elif not should_show and self.mini.isVisible():
            self.mini.hide()

    def _apply_translation_visibility(self):
        if getattr(self, "_ui_hidden", False):
            return
        if getattr(self, "translation_window", None) is None:
            return
        if self.cfg.app_paused:
            if self.translation_window.isVisible():
                self.translation_window.hide()
            return
        label = self.last_translation_label or get_target_lang_label_text(self.cfg.ui_lang, self.cfg.target_lang)
        if self.cfg.show_translation_window and (self.last_translation_text or "").strip():
            if not self._allow_translation_window and not self.translation_window.isVisible():
                return
            self.translation_window.set_translation(self.last_translation_text, label)
            if not self.translation_window.isVisible():
                self.translation_window.show()
        else:
            if self.translation_window.isVisible():
                self.translation_window.set_translation("", label)
                self.translation_window.hide()

    def _toggle_app_pause(self):
        self._set_app_paused(not self.cfg.app_paused)
