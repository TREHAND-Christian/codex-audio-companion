from PySide6.QtCore import Qt
import copy

from PySide6.QtWidgets import QApplication, QDialog

from .ui import OptionsDialog


class OptionsMixin:
    def _open_options(self):
        if getattr(self, "_options_dialog", None) is not None and self._options_dialog.isVisible():
            self._options_dialog.raise_()
            self._options_dialog.activateWindow()
            return
        _cfg_snapshot = copy.deepcopy(self.cfg)
        dlg = OptionsDialog(
            self.cfg,
            self.tts,
            on_live_change=self._refresh_ui,
            on_target_lang_change=self._restart_reading_with_new_target,
            get_detected_lang=lambda: self.last_detected_lang,
            parent=None,
        )
        if self.cfg.options_pos_x >= 0 and self.cfg.options_pos_y >= 0:
            dlg.move(self.cfg.options_pos_x, self.cfg.options_pos_y)
        else:
            screen = QApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                x = int(geo.x() + (geo.width() - dlg.width()) / 2)
                y = int(geo.y() + (geo.height() - dlg.height()) / 2)
                dlg.move(x, y)
        dlg.positionChanged.connect(self._on_options_position_changed)
        self._options_dialog = dlg

        def on_finished(result: int):
            if result == QDialog.Accepted:
                # Commit changes
                dlg.apply_to_config()
            else:
                # Revert any live changes applied while the dialog was open
                for k, v in vars(_cfg_snapshot).items():
                    setattr(self.cfg, k, copy.deepcopy(v))

            # Re-apply effects and UI
            self._apply_window_flags()
            self.mini.set_draggable(self.cfg.mini_bar_draggable)
            self._apply_position()
            self._refresh_ui()
            self._options_dialog = None

        dlg.finished.connect(on_finished)
        dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dlg.show()
        dlg.installEventFilter(self)
        self._raise_windows()
