from PySide6.QtCore import Qt, QSize, QSignalBlocker, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGroupBox, QCheckBox, QHBoxLayout, QLabel, QComboBox,
    QSlider, QPushButton, QStyle, QMessageBox
)

from ..memory_store import AppState

from .options_data import (
    LANG_VOICE_HINT,
    TARGET_LANG_LABELS,
    UI_LANG_LABELS,
    UI_TRANSLATIONS,
    build_announce_phrases,
)
from .options_widgets import _LangCombo
from .ui_utils import apply_topmost, raise_chain

# googletrans optional
try:
    from googletrans import Translator
except Exception:
    Translator = None


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


class OptionsDialog(QDialog):
    positionChanged = Signal(int, int)
    def __init__(
        self,
        cfg: AppState,
        tts,
        on_live_change=None,
        on_target_lang_change=None,
        get_detected_lang=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Options - SpeachCodexGPT")
        self.setModal(False)
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.cfg = cfg
        if self.cfg.voice_per_lang is None:
            self.cfg.voice_per_lang = {}
        self.tts = tts
        self._orig = AppState(**cfg.__dict__)
        self._on_live_change_cb = on_live_change
        self._on_target_lang_change_cb = on_target_lang_change
        self._get_detected_lang_cb = get_detected_lang
        self._last_voice_announce = ""
        self._last_rate_announce = ""
        self._last_announcements = {}
        self._pending_announce_key = ""
        self._pending_announce_phrase = ""
        self._last_target_code = (cfg.target_lang or "fr").lower()
        self._saved_target_code = self._last_target_code
        self._lang_available = {}
        self._lang_voice_hint = LANG_VOICE_HINT

        layout = QVBoxLayout(self)

        grp_general = QGroupBox("Général")
        gl_general = QVBoxLayout(grp_general)

        row_ui_lang = QHBoxLayout()
        self.lbl_ui_lang = QLabel("Langue interface :")
        row_ui_lang.addWidget(self.lbl_ui_lang)
        self.cmb_ui_lang = QComboBox()
        for label, code in UI_LANG_LABELS:
            self.cmb_ui_lang.addItem(label, code)
        cur_ui_lang = (cfg.ui_lang or cfg.target_lang or "fr").lower()
        idx = self.cmb_ui_lang.findData(cur_ui_lang)
        if idx >= 0:
            self.cmb_ui_lang.setCurrentIndex(idx)
        else:
            self.cmb_ui_lang.setCurrentIndex(0)
        row_ui_lang.addWidget(self.cmb_ui_lang, 1)
        gl_general.addLayout(row_ui_lang)

        self.chk_auto_read = QCheckBox("Lecture automatique des nouvelles réponses")
        self.chk_auto_read.setChecked(cfg.auto_read_new_responses)
        gl_general.addWidget(self.chk_auto_read)

        self.chk_bar_top = QCheckBox("Afficher la barre flottante")
        self.chk_bar_top.setChecked(cfg.mini_bar_always_on_top)
        gl_general.addWidget(self.chk_bar_top)

        self.chk_bar_start = QCheckBox("Afficher la barre flottante au démarrage")
        self.chk_bar_start.setChecked(cfg.show_mini_bar_on_start)
        gl_general.addWidget(self.chk_bar_start)

        self.chk_show_text = QCheckBox("Afficher la fenêtre de traduction")
        self.chk_show_text.setChecked(cfg.show_translation_window)
        gl_general.addWidget(self.chk_show_text)

        layout.addWidget(grp_general)

        grp_tts = QGroupBox("TTS")
        gl = QVBoxLayout(grp_tts)

        self.chk_app_pause = QCheckBox("Mettre le service en pause")
        self.chk_app_pause.setChecked(cfg.app_paused)
        gl.addWidget(self.chk_app_pause)

        self.chk_mute = QCheckBox("Muet (coupe la lecture)")
        self.chk_mute.setChecked(cfg.tts_mute)
        gl.addWidget(self.chk_mute)

        row_voice = QHBoxLayout()
        self.lbl_voice = QLabel("Voix :")
        row_voice.addWidget(self.lbl_voice)
        self.cmb_voice = QComboBox()
        self._refresh_voice_list((cfg.target_lang or "fr").lower(), cfg.tts_voice_id or "")
        preferred = (self.cfg.voice_per_lang or {}).get((cfg.target_lang or "").lower(), "")
        if preferred:
            idx = self.cmb_voice.findData(preferred)
            if idx >= 0:
                self.cmb_voice.setCurrentIndex(idx)
                self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""

        row_voice.addWidget(self.cmb_voice, 1)
        gl.addLayout(row_voice)

        row_rate = QHBoxLayout()
        self.lbl_rate_caption = QLabel("Vitesse :")
        row_rate.addWidget(self.lbl_rate_caption)
        self.btn_rate_minus = QPushButton("")
        self.btn_rate_plus = QPushButton("")
        self.btn_rate_minus.setFixedSize(28, 24)
        self.btn_rate_plus.setFixedSize(28, 24)
        self._set_btn_icon(self.btn_rate_minus, QStyle.SP_ArrowLeft)
        self._set_btn_icon(self.btn_rate_plus, QStyle.SP_ArrowRight)
        self.sld_rate = QSlider(Qt.Horizontal)
        self.sld_rate.setRange(0, 200)
        self.sld_rate.setFixedWidth(200)
        rate_pct = int(clamp(int(round(cfg.tts_rate * 100)), 0, 200))
        self.sld_rate.setValue(rate_pct)
        self.lbl_rate = QLabel(f"{self.sld_rate.value()}%")
        self.lbl_rate.setFixedWidth(50)
        self.sld_rate.valueChanged.connect(
            lambda v: self.lbl_rate.setText(f"{v}%")
        )
        self.sld_rate.valueChanged.connect(self._on_rate_change)
        self.sld_rate.sliderReleased.connect(self._announce_rate)
        self.btn_rate_minus.clicked.connect(lambda: self._bump_slider(self.sld_rate, -5, self._announce_rate))
        self.btn_rate_plus.clicked.connect(lambda: self._bump_slider(self.sld_rate, 5, self._announce_rate))
        row_rate.addWidget(self.btn_rate_minus)
        row_rate.addWidget(self.sld_rate, 1)
        row_rate.addWidget(self.btn_rate_plus)
        row_rate.addWidget(self.lbl_rate)
        gl.addLayout(row_rate)

        row_vol = QHBoxLayout()
        self.lbl_vol_caption = QLabel("Volume :")
        row_vol.addWidget(self.lbl_vol_caption)
        self.btn_vol_minus = QPushButton("")
        self.btn_vol_plus = QPushButton("")
        self.btn_vol_minus.setFixedSize(28, 24)
        self.btn_vol_plus.setFixedSize(28, 24)
        self._set_btn_icon(self.btn_vol_minus, QStyle.SP_ArrowLeft)
        self._set_btn_icon(self.btn_vol_plus, QStyle.SP_ArrowRight)
        self.sld_vol = QSlider(Qt.Horizontal)
        self.sld_vol.setRange(0, 100)
        self.sld_vol.setFixedWidth(200)
        self.sld_vol.setValue(clamp(cfg.tts_volume, 0, 100))
        self.lbl_vol = QLabel(f"{self.sld_vol.value()}%")
        self.lbl_vol.setFixedWidth(50)
        self.sld_vol.valueChanged.connect(lambda v: self.lbl_vol.setText(f"{v}%"))
        self.sld_vol.valueChanged.connect(self._on_live_change)
        self.sld_vol.sliderReleased.connect(self._announce_volume)
        self.btn_vol_minus.clicked.connect(lambda: self._bump_slider(self.sld_vol, -5, self._announce_volume))
        self.btn_vol_plus.clicked.connect(lambda: self._bump_slider(self.sld_vol, 5, self._announce_volume))
        row_vol.addWidget(self.btn_vol_minus)
        row_vol.addWidget(self.sld_vol, 1)
        row_vol.addWidget(self.btn_vol_plus)
        row_vol.addWidget(self.lbl_vol)
        gl.addLayout(row_vol)

        self.btn_test = QPushButton("Tester la voix")
        self.btn_test.clicked.connect(self.on_test)
        gl.addWidget(self.btn_test)

        self.chk_translate = QCheckBox("Traduire si nécessaire (googletrans)")
        self.chk_translate.setChecked(cfg.translate_enabled)
        self.chk_translate.setEnabled(Translator is not None)
        if Translator is None:
            self.chk_translate.setText("Traduction indisponible (Python 3.13+ / googletrans)")
        gl.addWidget(self.chk_translate)

        row_tgt = QHBoxLayout()
        self.lbl_target = QLabel("Langue cible :")
        row_tgt.addWidget(self.lbl_target)
        self.cmb_target = _LangCombo()
        self.cmb_target.setEditable(True)
        self.cmb_target.setInsertPolicy(QComboBox.NoInsert)
        self.cmb_target.setMaxCount(20)
        try:
            self.cmb_target.lineEdit().setMaxLength(8)
        except Exception:
            pass
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
            pass

        def is_available(code: str) -> bool:
            code = code.lower()
            return any(l.startswith(code) for l in available_langs)

        for label, code in TARGET_LANG_LABELS:
            available = is_available(code)
            self._lang_available[code] = available
            self.cmb_target.addItem(label, code)
            model = self.cmb_target.model()
            if isinstance(model, QStandardItemModel):
                item = model.item(self.cmb_target.count() - 1)
                if item is not None:
                    item.setIcon(self._speaker_icon(available))
                    item.setForeground(QColor(0, 0, 0))
        model_ui = self.cmb_ui_lang.model()
        if isinstance(model_ui, QStandardItemModel):
            for i in range(self.cmb_ui_lang.count()):
                code = self.cmb_ui_lang.itemData(i)
                if not isinstance(code, str):
                    continue
                available = is_available(code)
                item = model_ui.item(i)
                if item is not None:
                    item.setIcon(self._speaker_icon(available))
                    item.setForeground(QColor(0, 0, 0))
        cur_lang = (cfg.target_lang or "fr").lower()
        idx = self.cmb_target.findData(cur_lang)
        if idx >= 0:
            self.cmb_target.setCurrentIndex(idx)
        else:
            self.cmb_target.setEditText(cur_lang)
        self._saved_target_code = self._get_target_lang_code()
        self._apply_detected_target_lang_if_needed()
        row_tgt.addWidget(self.cmb_target, 1)
        gl.addLayout(row_tgt)

        layout.addWidget(grp_tts)
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_ok.setDefault(True)
        self.btn_ok.setMinimumWidth(90)
        self.btn_cancel.setMinimumWidth(90)
        btn_style = (
            "QPushButton {"
            "padding: 6px 12px;"
            "border: 1px solid #c8c8c8;"
            "border-radius: 4px;"
            "background: #f7f7f7;"
            "}"
            "QPushButton:hover {"
            "background: #efefef;"
            "}"
            "QPushButton:pressed {"
            "background: #e6e6e6;"
            "}"
        )
        self.btn_ok.setStyleSheet(btn_style)
        self.btn_cancel.setStyleSheet(btn_style)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)

        self.chk_app_pause.stateChanged.connect(self._on_app_pause_change)
        self.chk_mute.stateChanged.connect(self._on_mute_change)
        self.cmb_voice.currentIndexChanged.connect(self._on_voice_change)
        self.chk_translate.stateChanged.connect(self._on_translate_change)
        self.cmb_target.currentTextChanged.connect(self._on_target_change)
        self.cmb_target.popupShown.connect(self._refresh_target_availability)
        self.cmb_ui_lang.currentIndexChanged.connect(self._on_ui_lang_change)

        self.grp_tts = grp_tts
        self.grp_general = grp_general
        self._apply_ui_language((cfg.ui_lang or cfg.target_lang or "fr").lower())
        self.chk_auto_read.stateChanged.connect(self._on_auto_read_change)
        self.chk_bar_top.stateChanged.connect(self._on_bar_top_change)
        self.chk_bar_start.stateChanged.connect(self._on_bar_start_change)
        self.chk_show_text.stateChanged.connect(self._on_show_text_change)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())
        self.setSizeGripEnabled(False)
        self._apply_tts_enabled(getattr(cfg, 'tts_enabled', True))

    def _set_btn_icon(self, btn: QPushButton, standard_icon: QStyle.StandardPixmap):
        icon = self.style().standardIcon(standard_icon)
        size = QSize(12, 12)
        base = icon.pixmap(size)
        tinted = QPixmap(base.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, base)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(0, 120, 215))
        painter.end()
        btn.setIcon(QIcon(tinted))
        btn.setIconSize(size)

    def on_test(self):
        tmp = AppState(**self.cfg.__dict__)
        tmp.tts_enabled = True
        tmp.tts_mute = False
        tmp.tts_rate = self.sld_rate.value() / 100.0
        tmp.tts_volume = self.sld_vol.value()
        tmp.tts_voice_id = self.cmb_voice.currentData() or ""
        self.tts.speak("Test de lecture SpeachCodexGPT. Bonjour !", tmp)

    def reject(self):
        super().reject()

    def apply_to_config(self):
        self.cfg.app_paused = self.chk_app_pause.isChecked()
        self.cfg.tts_mute = self.chk_mute.isChecked()
        self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""
        self.cfg.tts_rate = self.sld_rate.value() / 100.0
        self.cfg.tts_volume = self.sld_vol.value()

        self.cfg.translate_enabled = self.chk_translate.isChecked() if Translator is not None else False
        self.cfg.target_lang = self._get_target_lang_code()
        self.cfg.ui_lang = self._get_ui_lang_code()

        self.cfg.auto_read_new_responses = self.chk_auto_read.isChecked()
        self.cfg.mini_bar_always_on_top = self.chk_bar_top.isChecked()
        self.cfg.show_mini_bar_on_start = self.chk_bar_start.isChecked()

    def _build_preview_cfg(self) -> AppState:
        tmp = AppState(**self.cfg.__dict__)
        tmp.tts_enabled = True
        tmp.tts_mute = False
        tmp.tts_rate = self.sld_rate.value() / 100.0
        tmp.tts_volume = self.sld_vol.value()
        tmp.tts_voice_id = self.cmb_voice.currentData() or ""
        return tmp

    def _build_preview_cfg_for_ui(self) -> AppState | None:
        tmp = AppState(**self.cfg.__dict__)
        tmp.tts_enabled = True
        tmp.tts_mute = False
        tmp.tts_rate = self.sld_rate.value() / 100.0
        tmp.tts_volume = self.sld_vol.value()
        ui_lang = self._get_ui_lang_code()
        voice_id = self._default_voice_for_lang(ui_lang)
        if not voice_id:
            return None
        tmp.tts_voice_id = voice_id
        return tmp

    def _default_voice_for_lang(self, lang: str) -> str:
        lang = (lang or "").lower()
        items = self.tts.list_voices() or []
        items.sort(key=lambda x: (0 if x.get("engine") == "winrt" else 1, x.get("name", "")))
        for v in items:
            langs = [str(x).lower() for x in (v.get("languages") or [])]
            if any(l.startswith(lang) for l in langs):
                return v.get("id") or ""
        return ""

    def _apply_live_all(self):
        self.cfg.app_paused = self.chk_app_pause.isChecked()
        self.cfg.tts_mute = self.chk_mute.isChecked()
        self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""
        self.cfg.tts_rate = self.sld_rate.value() / 100.0
        self.cfg.tts_volume = self.sld_vol.value()
        self.cfg.translate_enabled = self.chk_translate.isChecked() if Translator is not None else False
        self.cfg.target_lang = self._get_target_lang_code()
        self.cfg.ui_lang = self._get_ui_lang_code()
        self.cfg.auto_read_new_responses = self.chk_auto_read.isChecked()
        self.cfg.mini_bar_always_on_top = self.chk_bar_top.isChecked()
        self.cfg.show_mini_bar_on_start = self.chk_bar_start.isChecked()
        self.cfg.show_translation_window = self.chk_show_text.isChecked()
        self.cfg.show_translation_window = self.chk_show_text.isChecked()
        if callable(self._on_live_change_cb):
            self._on_live_change_cb()

    def _apply_tts_live_change(self):
        if not (self.tts.is_speaking() or self.tts.is_paused()):
            return
        if self.cfg.tts_mute or not self.cfg.tts_enabled:
            try:
                self.tts.stop()
            except Exception:
                pass
            return
        if hasattr(self.tts, "apply_live_cfg"):
            self.tts.apply_live_cfg(self.cfg)
        else:
            self.tts.pause()
            self.tts.resume()

    def _get_effective_target_lang(self) -> str:
        translate_enabled = False
        try:
            translate_enabled = self.chk_translate.isChecked() if Translator is not None else False
        except Exception:
            translate_enabled = False
        if translate_enabled:
            return self._get_target_lang_code()
        detected = ""
        if callable(self._get_detected_lang_cb):
            detected = (self._get_detected_lang_cb() or "").strip().lower()
        if detected and detected != "?":
            return detected
        return self._get_target_lang_code()

    def _get_voice_list_lang(self) -> str:
        return self._get_effective_target_lang()

    def refresh_voice_list_from_context(self):
        self._apply_detected_target_lang_if_needed()
        self._refresh_voice_list(self._get_voice_list_lang(), self.cfg.tts_voice_id)

    def _apply_detected_target_lang_if_needed(self):
        translate_enabled = self.chk_translate.isChecked() if Translator is not None else False
        if translate_enabled:
            return
        detected = ""
        if callable(self._get_detected_lang_cb):
            detected = (self._get_detected_lang_cb() or "").strip().lower()
        if not detected or detected == "?":
            return
        self._force_target_lang(detected)
        self._refresh_voice_list(detected, self.cfg.tts_voice_id)
        if self.cmb_voice.count() > 0:
            self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""

    def _force_target_lang(self, lang: str):
        with QSignalBlocker(self.cmb_target):
            idx = self.cmb_target.findData(lang)
            if idx >= 0:
                self.cmb_target.setCurrentIndex(idx)
            else:
                self.cmb_target.setEditText(lang)
        self.cfg.target_lang = lang
        self._last_target_code = lang

    def sync_mute_from_config(self):
        with QSignalBlocker(self.chk_mute):
            self.chk_mute.setChecked(self.cfg.tts_mute)

    def sync_app_pause_from_config(self):
        with QSignalBlocker(self.chk_app_pause):
            self.chk_app_pause.setChecked(self.cfg.app_paused)

    def sync_show_text_from_config(self):
        with QSignalBlocker(self.chk_show_text):
            self.chk_show_text.setChecked(self.cfg.show_translation_window)

    def _on_live_change(self, *args):
        self._apply_live_all()
        self._apply_tts_live_change()

    def _on_voice_change(self, *args):
        self._apply_live_all()
        self._apply_tts_live_change()
        lang = (self.cfg.target_lang or "").lower()
        voice_id = self.cmb_voice.currentData() or ""
        if lang:
            self.cfg.voice_per_lang[lang] = voice_id
        voice_label = (self.cmb_voice.currentText() or "").split("(")[0].strip()
        if not voice_label:
            return
        if voice_label == self._last_voice_announce:
            return
        self._last_voice_announce = voice_label
        self._announce("voice", voice_label=voice_label)

    def _on_rate_change(self, *args):
        self._apply_live_all()
        self._apply_tts_live_change()

    def _announce_rate(self):
        rate_pct = int(self.sld_rate.value())
        rate_text = str(rate_pct)
        if rate_text == self._last_rate_announce:
            return
        self._last_rate_announce = rate_text
        self._announce("rate", rate_pct=rate_text)

    def _announce_volume(self):
        vol = int(self.sld_vol.value())
        self._announce("volume", volume=vol)

    def _on_app_pause_change(self, *args):
        self._apply_live_all()
        self._announce("app_paused", paused=self.chk_app_pause.isChecked())

    def _on_mute_change(self, *args):
        self._apply_live_all()
        self._announce("tts_mute", muted=self.chk_mute.isChecked())

    def _on_translate_change(self, *args):
        self._apply_live_all()
        self._announce("translate", enabled=self.chk_translate.isChecked())
        if self._lang_available.get(lang, False):
            self._apply_tts_enabled(True)
        if self.chk_translate.isChecked():
            self.cmb_target.setEnabled(True)
            if self._saved_target_code:
                self._force_target_lang(self._saved_target_code)
            self._on_target_change()
        else:
            self._saved_target_code = self._get_target_lang_code()
            self._apply_detected_target_lang_if_needed()
            self.cmb_target.setEnabled(False)
            self._on_target_change()
        self._refresh_voice_list(self._get_voice_list_lang(), self.cfg.tts_voice_id)
        if self.cmb_voice.count() > 0:
            self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""
        self._apply_tts_live_change()

    def _on_ui_lang_change(self, *args):
        self._apply_live_all()
        self._apply_ui_language(self._get_ui_lang_code())

    def _on_target_change(self, *args):
        lang = self._get_target_lang_code()
        if not self._lang_available.get(lang, False) and self.cmb_target.isEnabled():
            msg = QMessageBox(self)
            title, body = self._speech_unavailable_text(self._get_ui_lang_code())
            msg.setWindowTitle(title)
            msg.setTextFormat(Qt.RichText)
            msg.setText(body)
            msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            msg.setDefaultButton(QMessageBox.Cancel)
            res = msg.exec()
            if res != QMessageBox.Ok:
                with QSignalBlocker(self.cmb_target):
                    idx = self.cmb_target.findData(self._last_target_code)
                    if idx >= 0:
                        self.cmb_target.setCurrentIndex(idx)
                    else:
                        self.cmb_target.setEditText(self._last_target_code)
                return
            self._apply_tts_enabled(False)
            if Translator is not None:
                with QSignalBlocker(self.chk_translate):
                    self.chk_translate.setChecked(True)

        if self._lang_available.get(lang, False):
            self._apply_tts_enabled(True)
        if self.chk_translate.isChecked():
            self._saved_target_code = lang
            self.cfg.target_lang = lang
        else:
            lang = self._get_effective_target_lang()
            self.cfg.target_lang = lang
        self._last_target_code = lang
        self._refresh_voice_list(self._get_voice_list_lang(), self.cfg.tts_voice_id)
        if self.cmb_voice.count() > 0:
            preferred = (self.cfg.voice_per_lang or {}).get(lang, "")
            if preferred:
                idx = self.cmb_voice.findData(preferred)
                if idx >= 0:
                    with QSignalBlocker(self.cmb_voice):
                        self.cmb_voice.setCurrentIndex(idx)
            self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""
            if self.cfg.tts_voice_id:
                self.cfg.voice_per_lang[lang] = self.cfg.tts_voice_id
        self._apply_live_all()
        if callable(self._on_target_lang_change_cb):
            self._on_target_lang_change_cb(self.tts.is_speaking())
        self._announce("target_lang", target_lang=lang)

    def _on_auto_read_change(self, *args):
        self._apply_live_all()
        self._announce("auto_read", enabled=self.chk_auto_read.isChecked())

    def _on_bar_top_change(self, *args):
        self._apply_live_all()
        self._announce("bar_top", enabled=self.chk_bar_top.isChecked())

    def _on_bar_start_change(self, *args):
        self._apply_live_all()
        self._announce("bar_start", enabled=self.chk_bar_start.isChecked())

    def _on_show_text_change(self, *args):
        self._apply_live_all()
        self.cfg.show_translation_window_set = True
        self._announce("show_text", enabled=self.chk_show_text.isChecked())

    def _speak_once(self, key: str, phrase: str, force: bool = False):
        if not force and self._last_announcements.get(key) == phrase:
            return
        self._last_announcements[key] = phrase
        cfg = self._build_preview_cfg_for_ui()
        if cfg is None:
            return
        self.tts.speak(phrase, cfg, ui_announcement=True)

    def _announce(self, key: str, **kwargs):
        ui_lang = self._get_ui_lang_code()
        phrase = self._phrase_for(key, ui_lang, **kwargs)
        if not phrase:
            return
        if self.tts.is_speaking() or self.tts.is_paused():
            self._pending_announce_key = key
            self._pending_announce_phrase = phrase
            try:
                self.tts.stop()
            except Exception:
                pass
            if not hasattr(self, "_announce_timer"):
                self._announce_timer = QTimer(self)
                self._announce_timer.setSingleShot(True)
                self._announce_timer.timeout.connect(self._flush_pending_announce)
            if not self._announce_timer.isActive():
                self._announce_timer.start(10)
            return
        self._speak_once(key, phrase, force=True)

    def _flush_pending_announce(self):
        phrase = self._pending_announce_phrase
        key = self._pending_announce_key
        if not phrase:
            return
        if self.tts.is_speaking() or self.tts.is_paused():
            self._announce_timer.start(10)
            return
        self._pending_announce_phrase = ""
        self._pending_announce_key = ""
        self._speak_once(key, phrase, force=True)

    def _phrase_for(self, key: str, ui_lang: str, **kwargs) -> str:
        base = (ui_lang or "fr").split("-")[0]
        voice_label = kwargs.get("voice_label", "")
        rate_pct = kwargs.get("rate_pct", "")
        volume = kwargs.get("volume", "")
        enabled = kwargs.get("enabled", False)
        muted = kwargs.get("muted", False)
        paused = kwargs.get("paused", False)
        target_lang = kwargs.get("target_lang", "")

        target_lang_phrase = self._target_lang_phrase(ui_lang, target_lang)
        phrases = build_announce_phrases(
            voice_label, rate_pct, volume, enabled, muted, paused, target_lang_phrase
        )
        return phrases.get(base, phrases["fr"]).get(key, "")

    def _refresh_voice_list(self, lang_code: str, current_voice_id: str):
        lang_code = (lang_code or "").lower()
        items = self.tts.list_voices() or []
        items.sort(key=lambda x: (0 if x.get("engine") == "winrt" else 1, x.get("name", "")))

        def matches_lang(v) -> bool:
            langs = [str(x).lower() for x in (v.get("languages") or [])]
            return any(l.startswith(lang_code) for l in langs) if lang_code else True

        filtered = [v for v in items if matches_lang(v)]

        with QSignalBlocker(self.cmb_voice):
            self.cmb_voice.clear()
            for v in filtered:
                self.cmb_voice.addItem(v["name"], v["id"])

            if current_voice_id:
                idx = self.cmb_voice.findData(current_voice_id)
                if idx >= 0:
                    self.cmb_voice.setCurrentIndex(idx)
                elif self.cmb_voice.count() > 0:
                    self.cmb_voice.setCurrentIndex(0)
            elif self.cmb_voice.count() > 0:
                self.cmb_voice.setCurrentIndex(0)

        if self.cmb_voice.count() > 0:
            self.cfg.tts_voice_id = self.cmb_voice.currentData() or ""

    def _get_target_lang_code(self) -> str:
        data = self.cmb_target.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip().lower()
        text = self.cmb_target.currentText().strip()
        return (text or "fr").lower()

    def _get_ui_lang_code(self) -> str:
        data = self.cmb_ui_lang.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip().lower()
        text = self.cmb_ui_lang.currentText().strip()
        return (text or self._get_target_lang_code()).lower()

    def _target_lang_phrase(self, ui_lang: str, target_lang: str) -> str:
        label_map = {code.lower(): label for label, code in TARGET_LANG_LABELS}
        label = label_map.get((target_lang or "").lower(), target_lang or "?")
        base = (ui_lang or "fr").split("-")[0]
        templates = {
            "fr": "la langue cible est {label}",
            "en": "the target language is {label}",
            "de": "die Zielsprache ist {label}",
            "es": "el idioma de destino es {label}",
            "it": "la lingua di destinazione è {label}",
            "pt": "o idioma de destino é {label}",
            "nl": "de doeltaal is {label}",
            "ru": "целевой язык — {label}",
            "ja": "ターゲット言語は{label}です",
            "zh": "目标语言是{label}",
            "ar": "اللغة المستهدفة هي {label}",
        }
        return templates.get(base, templates["fr"]).format(label=label)

    def _refresh_target_availability(self):
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
            pass

        def is_available(code: str) -> bool:
            code = code.lower()
            return any(l.startswith(code) for l in available_langs)

        self._lang_available.clear()
        model = self.cmb_target.model()
        for i in range(self.cmb_target.count()):
            code = self.cmb_target.itemData(i)
            if not isinstance(code, str):
                continue
            available = is_available(code)
            self._lang_available[code] = available
            if isinstance(model, QStandardItemModel):
                item = model.item(i)
                if item is not None:
                    item.setIcon(self._speaker_icon(available))
                    item.setForeground(QColor(0, 0, 0))

    def _speaker_icon(self, available: bool) -> QIcon:
        icon = self.style().standardIcon(QStyle.SP_MediaVolume)
        size = QSize(12, 12)
        base = icon.pixmap(size)
        tinted = QPixmap(base.size())
        tinted.fill(Qt.transparent)
        painter = QPainter(tinted)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, base)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), QColor(0, 160, 0) if available else QColor(200, 50, 50))
        painter.end()
        return QIcon(tinted)

    def _apply_ui_language(self, lang: str):
        lang = (lang or "fr").lower()
        key = lang.split("-")[0]
        t = UI_TRANSLATIONS
        tr = t.get(key, t["fr"])

        self.grp_tts.setTitle(tr["grp_tts"])
        self.grp_general.setTitle(tr.get("grp_general", tr.get("grp_beh", tr.get("grp_tts", ""))))
        self.chk_app_pause.setText(tr["app_paused"])
        self.chk_mute.setText(tr["tts_mute"])
        self.lbl_voice.setText(tr["voice"])
        self.lbl_rate_caption.setText(tr["rate"])
        self.lbl_vol_caption.setText(tr["volume"])
        self.btn_test.setText(tr["test"])
        if Translator is None:
            self.chk_translate.setText("Traduction indisponible (Python 3.13+ / googletrans)")
        else:
            self.chk_translate.setText(tr["translate"])
        self.lbl_ui_lang.setText(tr.get("ui_lang", "Langue interface :"))
        self.lbl_target.setText(tr["target"])
        self.chk_auto_read.setText(tr["auto_read"])
        self.chk_bar_top.setText(tr["bar_top"])
        self.chk_bar_start.setText(tr["bar_start"])
        self.chk_show_text.setText(tr["show_text"])
        self.btn_ok.setText(tr["ok"])
        self.btn_cancel.setText(tr["cancel"])

    def _apply_tts_enabled(self, enabled: bool):
        enabled = bool(enabled)
        self.cfg.tts_enabled = enabled
        widgets = [
            self.chk_mute,
            self.cmb_voice,
            self.lbl_voice,
            self.lbl_rate_caption,
            self.btn_rate_minus,
            self.btn_rate_plus,
            self.sld_rate,
            self.lbl_rate,
            self.lbl_vol_caption,
            self.btn_vol_minus,
            self.btn_vol_plus,
            self.sld_vol,
            self.lbl_vol,
            self.btn_test,
        ]
        for w in widgets:
            w.setEnabled(enabled)
        if not enabled:
            try:
                self.tts.stop()
            except Exception:
                pass

    def _speech_unavailable_text(self, lang_code: str) -> tuple[str, str]:
        code = (lang_code or "").split("-")[0].lower()
        messages = {
            "fr": (
                "Synthèse vocale indisponible",
                "La synthèse vocale n'est pas disponible pour cette langue.<br><br>"
                "Tu peux quand même utiliser la traduction texte.",
            ),
            "en": (
                "Speech synthesis unavailable",
                "Speech synthesis is not available for this language.<br><br>"
                "You can still use text translation.",
            ),
            "de": (
                "Sprachausgabe nicht verfügbar",
                "Die Sprachausgabe ist für diese Sprache nicht verfügbar.<br><br>"
                "Du kannst die Textübersetzung trotzdem verwenden.",
            ),
            "es": (
                "Síntesis de voz no disponible",
                "La síntesis de voz no está disponible para este idioma.<br><br>"
                "Puedes seguir usando la traducción de texto.",
            ),
            "it": (
                "Sintesi vocale non disponibile",
                "La sintesi vocale non è disponibile per questa lingua.<br><br>"
                "Puoi comunque usare la traduzione testo.",
            ),
            "pt": (
                "Síntese de voz indisponível",
                "A síntese de voz não está disponível para este idioma.<br><br>"
                "Você ainda pode usar a tradução de texto.",
            ),
            "nl": (
                "Spraaksynthese niet beschikbaar",
                "Spraaksynthese is niet beschikbaar voor deze taal.<br><br>"
                "Je kunt nog steeds de tekstvertaling gebruiken.",
            ),
            "ru": (
                "Синтез речи недоступен",
                "Синтез речи недоступен для этого языка.<br><br>"
                "Вы все равно можете использовать перевод текста.",
            ),
            "ja": (
                "音声合成は利用できません",
                "この言語では音声合成を利用できません。<br><br>"
                "テキスト翻訳は引き続き利用できます。",
            ),
            "zh": (
                "语音合成不可用",
                "该语言不支持语音合成。<br><br>"
                "仍可使用文本翻译。",
            ),
            "ar": (
                "تحويل النص إلى كلام غير متاح",
                "تحويل النص إلى كلام غير متاح لهذه اللغة.<br><br>"
                "يمكنك الاستمرار في استخدام ترجمة النص.",
            ),
        }
        return messages.get(code, messages["fr"])

    def moveEvent(self, event):
        self.positionChanged.emit(self.x(), self.y())
        super().moveEvent(event)


