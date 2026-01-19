import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QStyle

from .ui.ui_utils import tint_icon


class TrayMixin:
    def _style_icon(self, sp: QStyle.StandardPixmap):
        return QApplication.style().standardIcon(sp)
    def _tint_icon(self, icon: QIcon, color: QColor) -> QIcon:
        return tint_icon(icon, color, size=16)
    def _idle_tray_icon(self, muted: bool, led_color: QColor) -> QIcon:
        size = 16
        composed = QPixmap(size, size)
        composed.fill(Qt.transparent)
        painter = QPainter(composed)
        painter.setRenderHint(QPainter.Antialiasing, True)

        border = QColor(0, 0, 0, 180)
        painter.setPen(border)
        painter.setBrush(led_color)
        dot = 6
        painter.drawEllipse(0, 0, dot, dot)

        base_size = 15
        base_x = 1
        base_y = 1
        base_icon = self._style_icon(QStyle.SP_MediaVolumeMuted if muted else QStyle.SP_MediaVolume)
        base_pix = base_icon.pixmap(base_size, base_size)
        outline_color = QColor(220, 60, 60) if muted else QColor(0, 200, 0)
        outline_pix = base_pix.copy()
        outline_painter = QPainter(outline_pix)
        outline_painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        outline_painter.fillRect(outline_pix.rect(), outline_color)
        outline_painter.end()
        for dx, dy in [
            (-1, 0),
            (1, 0),
            (0, -1),
            (0, 1),
            (-1, -1),
            (1, -1),
            (-1, 1),
            (1, 1),
        ]:
            painter.drawPixmap(base_x + dx, base_y + dy, outline_pix)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        painter.drawPixmap(base_x, base_y, base_pix)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if not muted:
            painter.setPen(QColor(0, 200, 0))
            painter.setBrush(Qt.NoBrush)
            rect = (base_x + 4, base_y + 1, 5, base_size - 2)
            painter.drawArc(*rect, 300 * 16, 120 * 16)
            rect2 = (base_x + 2, base_y, 7, base_size)
            painter.drawArc(*rect2, 300 * 16, 120 * 16)

        painter.end()
        return QIcon(composed)
    def _build_tray(self):
        # Keep reference to avoid GC
        self.tray = QSystemTrayIcon()
        self.tray.setToolTip("SpeachCodexGPT")

        menu = QMenu()

        self.act_pause_app = QAction("Mettre le service en pause")
        self.act_pause_app.triggered.connect(self._toggle_app_pause)
        menu.addAction(self.act_pause_app)

        self.act_mute = QAction("Muet (coupe la lecture)")
        self.act_mute.setCheckable(True)
        self.act_mute.triggered.connect(self._on_mute_toggle)

        self.act_options = QAction("⚙️ Options…")
        self.act_options.triggered.connect(self._open_options)
        menu.addAction(self.act_options)

        menu.addSeparator()

        self.act_quit = QAction("❌ Quitter")
        self.act_quit.triggered.connect(self._quit_app)
        menu.addAction(self.act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

        self._update_tray_icon()
        self.tray.show()
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_mini_bar()
        if reason == QSystemTrayIcon.DoubleClick:
            self._open_options()

    def _hidden_tray_icon(self) -> QIcon:
        """Small eye-with-slash icon (no external assets)."""
        size = 16
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)

        # Eye outline
        p.setPen(QColor(30, 30, 30, 220))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(2, 4, 12, 8)

        # Pupil
        p.setBrush(QColor(30, 30, 30, 220))
        p.drawEllipse(7, 7, 2, 2)

        # Slash
        p.setPen(QColor(220, 60, 60, 230))
        p.drawLine(3, 13, 13, 3)

        p.end()
        return QIcon(pm)


    def _update_tray_icon(self):
        if getattr(self, "tts", None) is not None and self.tts.is_ui_announcement():
            return
        # Hidden state: eye-slash icon
        if bool(getattr(self, "_ui_hidden", False)):
            self.tray.setIcon(self._hidden_tray_icon())
            self.tray.setToolTip("SpeachCodexGPT - Masqué")
            return

        # Normal state (unchanged)
        if self.tts.is_speaking() and not self.cfg.app_paused:
            base_icon = self._style_icon(QStyle.SP_MediaPlay)
            icon = self._tint_icon(base_icon, QColor(0, 200, 0))
            tip = "SpeachCodexGPT - Lecture"
        elif self.tts.is_paused() and not self.cfg.app_paused:
            base_icon = self._style_icon(QStyle.SP_MediaPause)
            icon = self._tint_icon(base_icon, QColor(0, 200, 0))
            tip = "SpeachCodexGPT - Pause lecture"
        elif self.cfg.app_paused:
            icon = self._idle_tray_icon(self.cfg.tts_mute, QColor(220, 60, 60))
            tip = "SpeachCodexGPT - Pause"
        else:
            icon = self._idle_tray_icon(self.cfg.tts_mute, QColor(0, 200, 0))
            tip = "SpeachCodexGPT - Actif"

        self.tray.setIcon(icon)
        self.tray.setToolTip(tip)

