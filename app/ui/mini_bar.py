from pathlib import Path

from PySide6.QtCore import Signal, Qt, QSize, QEvent
from PySide6.QtGui import QColor, QPainter, QPainterPath, QIcon, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QAbstractButton, QApplication, QStyle

from .ui_utils import apply_topmost, raise_chain, tint_icon

class MiniBar(QWidget):
    positionChanged = Signal(int, int)
    playPauseClicked = Signal()
    stopClicked = Signal()
    muteClicked = Signal()
    optionsClicked = Signal()

    def __init__(self):
        super().__init__()
        self._drag_enabled = False
        self._drag_active = False
        self._drag_offset = None
        self._drag_start_pos = None
        self._drag_pressed_button = None
        self._drag_moved = False
        self.setWindowTitle("SpeachCodexGPT")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFixedHeight(34)
        self.setObjectName("MiniBar")
        self._app_paused = False
        self._opts_icon_path = (
            Path(__file__).resolve().parents[2] / "assets" / "conf.svg"
        )

        self.lbl_status = QLabel("")
        self.lbl_status.setVisible(False)
        self.btn_play = QPushButton("")
        self.btn_stop = QPushButton("")
        self.btn_mute = QPushButton("")
        self.btn_opts = QPushButton("")

        for b in [self.btn_play, self.btn_stop, self.btn_mute, self.btn_opts]:
            b.setFixedSize(30, 26)
            b.setIconSize(QSize(16, 16))
            b.setFlat(True)
            b.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_mute)
        layout.addWidget(self.btn_opts)
        self._apply_icons()
        self._apply_style()

        self.btn_play.clicked.connect(self.playPauseClicked.emit)
        self.btn_stop.clicked.connect(self.stopClicked.emit)
        self.btn_mute.clicked.connect(self.muteClicked.emit)
        self.btn_opts.clicked.connect(self.optionsClicked.emit)

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def set_play_icon(self, playing: bool):
        icon = "media-playback-pause" if playing else "media-playback-start"
        fallback = "||" if playing else ">"
        self._set_button_icon(self.btn_play, icon, fallback, QColor(0, 120, 215))

    def set_mute_icon(self, muted: bool):
        icon = "audio-volume-muted" if muted else "audio-volume-high"
        fallback = "M" if muted else "V"
        self._set_button_icon(self.btn_mute, icon, fallback, QColor(0, 120, 215))

    def _apply_icons(self):
        style = QApplication.style()
        self._set_button_icon(self.btn_stop, "media-playback-stop", "[]", QColor(0, 120, 215))
        self._set_button_icon(self.btn_opts, str(self._opts_icon_path), "O")

    def _set_button_icon(
        self,
        button: QPushButton,
        icon_id: QStyle.StandardPixmap | str | None,
        fallback: str,
        tint: QColor | None = None,
    ):
        if icon_id is None:
            icon = self._gear_icon(tint or QColor(0, 0, 0))
        elif isinstance(icon_id, str):
            icon_path = Path(icon_id)
            if icon_path.exists():
                icon = QIcon(str(icon_path))
            else:
                icon = QIcon.fromTheme(icon_id)
        else:
            icon = QApplication.style().standardIcon(icon_id)
        if icon.isNull():
            button.setIcon(QIcon())
            button.setText(fallback)
        else:
            button.setText("")
            if tint is not None and icon_id is not None:
                icon = tint_icon(icon, tint)
            button.setIcon(icon)

    def _gear_icon(self, color: QColor) -> QIcon:
        size = 16
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(color, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        center = size / 2
        r_outer = 6
        r_inner = 3
        for i in range(8):
            angle = i * 45
            painter.save()
            painter.translate(center, center)
            painter.rotate(angle)
            painter.drawLine(r_inner + 1, 0, r_outer, 0)
            painter.restore()
        painter.drawEllipse(int(center - r_inner), int(center - r_inner), r_inner * 2, r_inner * 2)
        painter.end()
        return QIcon(pixmap)

    def set_active(self, app_paused: bool):
        self._app_paused = bool(app_paused)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(
            "QPushButton {"
            "background: transparent;"
            "border: none;"
            "padding: 0;"
            "}"
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        border_color = QColor(196, 58, 58) if self._app_paused else QColor(47, 191, 58)
        bg_color = QColor(230, 230, 230)
        border_width = 3
        radius = 6

        rect = self.rect().adjusted(
            border_width // 2,
            border_width // 2,
            -border_width // 2,
            -border_width // 2,
        )
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, bg_color)
        painter.setPen(border_color)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)


    def set_draggable(self, enabled: bool):
        self._drag_enabled = bool(enabled)


    def mousePressEvent(self, event):
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None
        if self._drag_enabled and Qt is not None and event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())
            if isinstance(child, QAbstractButton):
                super().mousePressEvent(event)
                return
            self._drag_active = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        if not self._drag_enabled or not isinstance(obj, QAbstractButton):
            return super().eventFilter(obj, event)

        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._drag_active = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_pressed_button = obj
            self._drag_moved = False
            event.accept()
            return True

        if event.type() == QEvent.MouseMove and self._drag_active and self._drag_pressed_button is obj:
            if self._drag_offset is not None:
                current_pos = event.globalPosition().toPoint()
                if self._drag_start_pos and (current_pos - self._drag_start_pos).manhattanLength() > 3:
                    self._drag_moved = True
                if self._drag_moved:
                    self.move(current_pos - self._drag_offset)
            event.accept()
            return True

        if (
            event.type() == QEvent.MouseButtonRelease
            and self._drag_active
            and self._drag_pressed_button is obj
            and event.button() == Qt.LeftButton
        ):
            if not self._drag_moved:
                obj.click()
            self._drag_active = False
            self._drag_offset = None
            self._drag_start_pos = None
            self._drag_pressed_button = None
            self.positionChanged.emit(self.x(), self.y())
            event.accept()
            return True

        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        if self._drag_enabled and self._drag_active and self._drag_offset is not None:
            pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            from PySide6.QtCore import Qt
        except Exception:
            Qt = None
        if self._drag_enabled and Qt is not None and event.button() == Qt.LeftButton:
            self._drag_active = False
            self._drag_offset = None
            self.positionChanged.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)

