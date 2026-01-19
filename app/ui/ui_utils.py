from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor, QPainter


def tint_icon(icon: QIcon, color: QColor, size: int = 16) -> QIcon:
    """Applique une couleur sur une icone."""
    pixmap = icon.pixmap(size, size)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return QIcon(pixmap)


def apply_topmost(win):
    """Force la fenetre au premier plan (top-most)."""
    win.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    win.setWindowFlag(Qt.Tool, True)
    if win.isVisible():
        win.hide()
    win.show()


def raise_chain(minibar, texte, options):
    """Garde l'ordre d'empilement entre les fenetres."""
    options.raise_()
    texte.raise_()
    minibar.raise_()
