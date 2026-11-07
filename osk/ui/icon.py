from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from osk.paths import resource_root

ASSET_DIR = resource_root() / "assets"


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        path = ASSET_DIR / f"icon-{size}.png"
        if path.is_file():
            icon.addFile(str(path), QSize(size, size))
    if not icon.isNull():
        return icon

    themed = QIcon.fromTheme("input-keyboard")
    if not themed.isNull():
        return themed

    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        scale = size / 64
        painter.setBrush(QColor(16, 20, 24))
        painter.setPen(QPen(QColor(61, 169, 252), max(1.0, 2 * scale)))
        painter.drawRoundedRect(
            QRectF(4 * scale, 14 * scale, 56 * scale, 36 * scale), 8 * scale, 8 * scale
        )
        painter.setPen(QPen(QColor(255, 255, 255, 210), max(1.0, 1.4 * scale)))
        for row in range(3):
            for column in range(6):
                x = 9 * scale + column * 8 * scale
                y = 21 * scale + row * 7 * scale
                painter.drawLine(QPointF(x, y), QPointF(x + 4 * scale, y))
        painter.end()
        icon.addPixmap(pixmap)
    return icon
