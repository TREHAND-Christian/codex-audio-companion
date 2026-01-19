from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtWidgets import QApplication


class WindowsMixin:
    def _apply_window_flags(self):
        flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        self.mini.setWindowFlags(flags)
        if self.mini.isVisible():
            self.mini.show()
    def _apply_position(self):
        if self.cfg.mini_bar_pos_x >= 0 and self.cfg.mini_bar_pos_y >= 0:
            self.mini.move(self.cfg.mini_bar_pos_x, self.cfg.mini_bar_pos_y)
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.mini.adjustSize()
        x = int(geo.x() + (geo.width() - self.mini.width()) / 2)
        y = int(geo.y() + 10)
        self.mini.move(x, y)
    def _on_position_changed(self, x: int, y: int):
        self.cfg.mini_bar_pos_x = int(x)
        self.cfg.mini_bar_pos_y = int(y)
        self.store.save(self.cfg)
    def _on_translation_position_changed(self, x: int, y: int):
        self.cfg.translation_pos_x = int(x)
        self.cfg.translation_pos_y = int(y)
        self.store.save(self.cfg)
    def _on_translation_size_changed(self, w: int, h: int):
        self.cfg.translation_size_w = int(w)
        self.cfg.translation_size_h = int(h)
        self.store.save(self.cfg)
    def _on_options_position_changed(self, x: int, y: int):
        self.cfg.options_pos_x = int(x)
        self.cfg.options_pos_y = int(y)
        self.store.save(self.cfg)
    def eventFilter(self, obj, event):
        # When interacting with Options, let it come above texte if it gets activated,
        # but keep the minibar always on top.
        if getattr(self, "_options_dialog", None) is not None and obj is self._options_dialog:
            et = event.type()
            if et in (QEvent.MouseButtonPress, QEvent.FocusIn, QEvent.WindowActivate):
                QTimer.singleShot(0, lambda: self._raise_windows(force_text=False))
        return super().eventFilter(obj, event)
    def _raise_windows(self, force_text: bool = False):
        """Keep desired stacking order.
        - minibar is always on top
        - texte is raised above Options only when force_text=True (e.g. when a new response is read)
        """
        if force_text and self.translation_window.isVisible():
            self.translation_window.raise_()
        if self.mini.isVisible():
            self.mini.raise_()
    def _toggle_mini_bar(self):
        """Toggle UI visibility from tray click/menu.

        Requirement:
        - keep existing trigger (tray click + menu) unchanged
        - when hiding, hide mini + texte + options
        - when showing, restore what was visible
        """
        hidden = bool(getattr(self, "_ui_hidden", False))

        if not hidden:
            # snapshot current visibility
            self._ui_vis_snapshot = {
                "mini": self.mini.isVisible(),
                "texte": getattr(self, "translation_window", None) is not None and self.translation_window.isVisible(),
                "options": getattr(self, "_options_dialog", None) is not None and self._options_dialog.isVisible(),
            }

            # hide all three
            if getattr(self, "_options_dialog", None) is not None:
                self._options_dialog.hide()
            if getattr(self, "translation_window", None) is not None:
                self.translation_window.hide()
            self.mini.hide()

            self._ui_hidden = True
        else:
            self._ui_hidden = False

            # restore mini
            self._apply_window_flags()
            if getattr(self, "_ui_vis_snapshot", {}).get("mini", True):
                self.mini.show()

            # restore texte
            if getattr(self, "_ui_vis_snapshot", {}).get("texte", False) and getattr(self, "translation_window", None) is not None:
                self.translation_window.show()

            # restore options (only if dialog still exists)
            if getattr(self, "_ui_vis_snapshot", {}).get("options", False) and getattr(self, "_options_dialog", None) is not None:
                self._options_dialog.show()

        self._refresh_ui()
