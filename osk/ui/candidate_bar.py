from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class CandidateBar(QWidget):
    selected = Signal(int)
    page_up = Signal()
    page_down = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preedit_text = ""
        self.lookup_visible = False
        self.preedit_visible = False
        self.buttons: list[QPushButton] = []
        self._labels: list[str] = []
        self._texts: list[str] = []
        self._cursor = -1
        self._has_prev = False
        self._has_next = False
        self._item_count = 0
        self.reserved = False
        self.setFixedHeight(38)
        self.setFocusPolicy(Qt.NoFocus)
        self.hide()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 5, 10, 5)
        outer.setSpacing(7)

        self.preedit = QLabel()
        self.preedit.setStyleSheet("color: white; font-size: 13px; background: transparent;")
        outer.addWidget(self.preedit)

        self.items = QWidget()
        self.items.setStyleSheet("background: transparent;")
        self.items_layout = QHBoxLayout(self.items)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(6)
        outer.addWidget(self.items, 1)

        self.prev_button = QPushButton("‹")
        self.next_button = QPushButton("›")
        for button, signal_ in ((self.prev_button, self.page_up), (self.next_button, self.page_down)):
            button.setFixedSize(24, 24)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(signal_.emit)
            outer.addWidget(button)

        self.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,16);"
            "  border: 1px solid rgba(255,255,255,32); border-radius: 5px;"
            "  padding: 2px 7px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(255,255,255,30); }"
            "QPushButton[selected=\"true\"] { background: rgba(61,169,252,120);"
            "  border-color: #3da9fc; }"
        )

    def set_reserved(self, reserved: bool) -> None:
        self.reserved = bool(reserved)
        self._sync_visibility()

    def clear(self) -> None:
        self._labels = []
        self._texts = []
        self._cursor = -1
        self._has_prev = False
        self._has_next = False
        self.preedit_text = ""
        self.preedit.setText("")
        self.lookup_visible = False
        self.preedit_visible = False
        self._clear_items()
        self.hide()

    def set_lookup(self, labels, texts, has_prev: bool, has_next: bool, cursor: int) -> None:
        self._labels = list(labels)
        self._texts = list(texts)
        self._has_prev = bool(has_prev)
        self._has_next = bool(has_next)
        self._cursor = int(cursor)
        self._rebuild_items()

    def set_lookup_visible(self, visible: bool) -> None:
        self.lookup_visible = bool(visible)
        self.prev_button.setVisible(self.lookup_visible and self._has_prev)
        self.next_button.setVisible(self.lookup_visible and self._has_next)
        self._sync_visibility()

    def set_preedit(self, text: str, caret: int = 0) -> None:
        self.preedit_text = text
        self.preedit.setText(text)
        self._sync_visibility()

    def set_preedit_visible(self, visible: bool) -> None:
        self.preedit_visible = bool(visible)
        self._sync_visibility()

    def set_cursor(self, cursor: int) -> None:
        self._cursor = int(cursor)
        self._rebuild_items()

    def _clear_items(self) -> None:
        self.buttons.clear()
        self._item_count = 0
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_items(self) -> None:
        self._clear_items()
        count = max(len(self._labels), len(self._texts))
        metrics = QFontMetrics(self.font())
        for index in range(count):
            label = self._labels[index] if index < len(self._labels) else ""
            text = self._texts[index] if index < len(self._texts) else ""
            if not text:
                continue
            if not label:
                note = QLabel(text)
                note.setStyleSheet(
                    "color: rgba(255,255,255,150); font-size: 12px; background: transparent;"
                )
                self.items_layout.addWidget(note)
                self._item_count += 1
                continue
            caption = f"{label} {text}".strip()
            button = QPushButton(metrics.elidedText(caption, Qt.ElideRight, 220))
            button.setToolTip(caption)
            button.setFocusPolicy(Qt.NoFocus)
            button.setProperty("selected", index == self._cursor)
            button.clicked.connect(lambda checked=False, value=index: self.selected.emit(value))
            self.items_layout.addWidget(button)
            self.buttons.append(button)
            self._item_count += 1
        self.items_layout.addStretch(1)
        self.prev_button.setVisible(self.lookup_visible and self._has_prev)
        self.next_button.setVisible(self.lookup_visible and self._has_next)
        self._sync_visibility()

    def _has_content(self) -> bool:
        return bool(self.preedit_text) or self._item_count > 0

    def _sync_visibility(self) -> None:
        if self.reserved:
            self.preedit.setVisible(
                bool(self.preedit_text) and (self.preedit_visible or self.lookup_visible)
            )
            self.setVisible(True)
            return
        visible = (self.lookup_visible or self.preedit_visible) and self._has_content()
        self.preedit.setVisible(bool(self.preedit_text) and (self.preedit_visible or self.lookup_visible))
        self.setVisible(visible)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255, 10))
        painter.setPen(QPen(QColor(61, 169, 252, 70), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
