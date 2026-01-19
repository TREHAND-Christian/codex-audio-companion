from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class _LangCombo(QComboBox):
    popupShown = Signal()

    def showPopup(self):
        self.popupShown.emit()
        super().showPopup()
