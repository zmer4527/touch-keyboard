from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QEventPoint, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from osk.core.layout import Key, Layout
from osk.core.state import CAPS_CODE, KeyboardState, MOD_PRESSED
from osk.ui.candidate_bar import CandidateBar
from osk.core.touch import TouchRouter

SIGNAL = QColor(61, 169, 252)
MOUSE_ID = -1 << 30
MIN_WIDTH = 640


def default_width(area: QRect) -> int:
    return min(1400, max(880, int(area.width() * 0.92)))


class KeyWidget(QWidget):
    GLOW_PRESS = 1.0
    GLOW_LIT = 0.62
    GLOW_LOCKED = 1.0

    def __init__(self, key: Key):
        super().__init__()
        self.key = key
        self.label = key.label
        self.pressed = False
        self.lit = False
        self.locked = False
        self._glow = 0.0
        self._target = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.valueChanged.connect(self._set_glow)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(0, 24)

    def _set_glow(self, value) -> None:
        self._glow = float(value)
        self.update()

    def glow(self) -> float:
        return self._glow

    def _desired(self) -> float:
        if self.pressed:
            return self.GLOW_PRESS
        if self.locked:
            return self.GLOW_LOCKED
        if self.lit:
            return self.GLOW_LIT
        return 0.0

    def set_state(self, label: str, pressed: bool, lit: bool, locked: bool) -> None:
        if (label, pressed, lit, locked) == (self.label, self.pressed, self.lit, self.locked):
            return
        self.label, self.pressed, self.lit, self.locked = label, pressed, lit, locked
        target = self._desired()
        if abs(target - self._target) > 0.001:
            self._target = target
            self._animation.stop()
            self._animation.setStartValue(self._glow)
            self._animation.setEndValue(target)
            self._animation.setDuration(90 if target > self._glow else 240)
            self._animation.setEasingCurve(QEasingCurve.OutCubic)
            self._animation.start()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(rect, 7, 7)
        if self._glow > 0.01:
            painter.setPen(QPen(QColor(61, 169, 252, min(255, int(160 * self._glow))), 1))
            painter.setBrush(QColor(61, 169, 252, min(255, int(120 * self._glow))))
            painter.drawRoundedRect(rect, 7, 7)
        font = QFont(self.font())
        font.setPointSize(9 if len(self.label) > 2 else 11)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(rect, Qt.AlignCenter, self.label)


class KeyboardWindow(QWidget):
    language_changed = Signal(str)
    visibility_changed = Signal(bool)

    def __init__(
        self,
        layout: Layout,
        state: KeyboardState,
        backend,
        lang: str = "en",
        palm_limit: float = 0,
        fn_visible: bool = True,
        notice: str = "",
        opacity: int = 70,
    ):
        super().__init__()
        self.layout_data = layout
        self.state = state
        self.backend = backend
        self.notice = notice
        self.lang = lang
        self.opacity_percent = max(20, min(100, int(opacity)))
        self.external_down: set[int] = set()
        self.external_caps = False
        self.tray_available = True
        self.track_keyboard_enabled = False
        self.on_track_keyboard = None
        self.modifier_mode = state.mode
        self.candidates_enabled = False
        self.candidates_requested = False
        self.candidates_error = ""
        self._candidate_controller = None
        self.palm_limit = palm_limit
        self.router = TouchRouter(state)
        self.keys: list[KeyWidget] = []
        self.header_touches: dict[int, QPushButton] = {}
        self.row_widgets: list[QWidget] = []
        self.fn_visible = True
        self.drag_touch: int | None = None
        self.drag_mouse = False
        self.drag_global_origin: QPointF | None = None
        self.drag_window_origin: QPointF | None = None
        self.setObjectName("root")
        self.setWindowTitle("Linux touch keyboard — DroidDeck PC layout")
        if notice:
            self.setWindowTitle(self.windowTitle() + " — " + notice)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(
            "QLabel { color: #c9d1d9; }"
            "QPushButton { color: white; background: rgba(255,255,255,22);"
            "  border: 1px solid rgba(255,255,255,38); border-radius: 7px;"
            "  font-weight: 600; }"
            "QPushButton:hover { background: rgba(255,255,255,38); }"
            "QPushButton:pressed { background: rgba(61,169,252,120); }"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title = QLabel(layout.title(lang))
        self.title.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.status = QLabel(self.backend.name)
        self.status.setStyleSheet("font-size: 12px; color: #8b949e;")
        self.minimize_button = self._header_button(self._minimize_label(), self.minimize)
        self.minimize_button.setToolTip(
            "最小化到托盘" if lang == "zh" else "Minimize to the system tray"
        )
        header.addWidget(self.title)
        header.addWidget(self.status, 1)
        header.addWidget(self.minimize_button)
        outer.addLayout(header)
        self.header_buttons = [self.minimize_button]

        self.candidate_bar = CandidateBar(self)
        outer.addWidget(self.candidate_bar)

        board = QVBoxLayout()
        board.setContentsMargins(0, 0, 0, 0)
        board.setSpacing(3)
        for row in layout.rows:
            holder = QWidget()
            line = QHBoxLayout(holder)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(3)
            for key in row:
                widget = KeyWidget(key)
                self.keys.append(widget)
                line.addWidget(widget, max(1, int(round(key.weight * 100))))
            self.row_widgets.append(holder)
            board.addWidget(holder, 1)
        outer.addLayout(board, 1)
        if not fn_visible:
            self.fn_visible = False
            self.row_widgets[0].setVisible(False)
        self.refresh()

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start()

    def _header_button(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.setFixedHeight(24)
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(slot)
        return button

    def _update_header_labels(self) -> None:
        self.title.setText(self.layout_data.title(self.lang))
        self.minimize_button.setText(self._minimize_label())

    def set_language(self, lang: str) -> None:
        if lang not in ("en", "zh") or lang == self.lang:
            return
        self.lang = lang
        self._update_header_labels()
        self.refresh()
        self.language_changed.emit(self.lang)

    def toggle_lang(self) -> None:
        self.set_language("zh" if self.lang == "en" else "en")

    def _available_area(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)

    def screen_available_area(self) -> QRect:
        return self._available_area()

    def size_percent(self) -> int:
        area = self._available_area()
        return round(self.width() * 100 / max(1, area.width()))

    def set_width_px(self, width: int) -> None:
        area = self._available_area()
        width = max(MIN_WIDTH, min(int(width), area.width() - 16))
        height = max(300, min(620, int(width * 0.38)))
        center = self.x() + self.width() // 2
        bottom = self.y() + self.height()
        x = max(area.left(), min(center - width // 2, area.right() - width))
        y = max(area.top(), min(bottom - height, area.bottom() - height))
        self.resize(width, height)
        self.move(x, y)

    def set_width_percent(self, percent: int) -> None:
        area = self._available_area()
        self.set_width_px(round(area.width() * percent / 100))

    def _minimize_label(self) -> str:
        return "最小化" if self.lang == "zh" else "Minimize"

    def minimize(self) -> None:
        if self.tray_available:
            self.hide()
        else:
            self.close()

    def set_opacity(self, percent: int) -> None:
        self.opacity_percent = max(20, min(100, int(percent)))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(16, 20, 24, round(self.opacity_percent * 255 / 100)))

    def set_fn_visible(self, visible: bool) -> None:
        visible = bool(visible)
        if self.fn_visible == visible:
            return
        self.fn_visible = visible
        self.row_widgets[0].setVisible(visible)
        self.release_all()

    def drag_at(self, position: QPointF) -> bool:
        point = position.toPoint()
        for handle in (self.title, self.status):
            if handle.rect().contains(handle.mapFrom(self, point)):
                return True
        return False

    def key_at(self, position: QPointF) -> int | None:
        point = position.toPoint()
        for widget in self.keys:
            if widget.isVisible() and widget.rect().contains(widget.mapFrom(self, point)):
                return widget.key.evdev
        return None

    def header_at(self, position: QPointF) -> QPushButton | None:
        point = position.toPoint()
        for button in self.header_buttons:
            if button.isVisible() and button.rect().contains(button.mapFrom(self, point)):
                return button
        return None

    def event(self, event) -> bool:
        kind = event.type()
        if kind in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            for point in event.points():
                if kind == QEvent.TouchEnd or point.state() == QEventPoint.Released:
                    self._touch_release(point.id(), point.position())
                else:
                    self._touch_move(
                        point.id(), point.position(), point.ellipseDiameters(), point.globalPosition()
                    )
            self.refresh()
            return True
        if kind == QEvent.TouchCancel:
            self.cancel_touches()
            return True
        if kind == QEvent.ApplicationDeactivate:
            self.release_all()
        return super().event(event)

    def _touch_move(
        self,
        touch_id: int,
        position: QPointF,
        diameters: QSize,
        global_position: QPointF | None = None,
    ) -> None:
        if self.palm_limit and max(diameters.width(), diameters.height()) > self.palm_limit:
            self._touch_release(touch_id, position)
            return
        if self.drag_touch == touch_id:
            current = global_position or QPointF(self.mapToGlobal(position.toPoint()))
            self._drag_to(current)
            return
        button = self.header_at(position)
        if button is not None:
            current = self.header_touches.get(touch_id)
            if current is button:
                return
            if current is not None:
                current.setDown(False)
            self.router.release(touch_id)
            self.header_touches[touch_id] = button
            button.setDown(True)
            return
        current = self.header_touches.pop(touch_id, None)
        if current is not None:
            current.setDown(False)
        if self.drag_at(position) and touch_id not in self.router.owner_by_touch:
            self.router.release(touch_id)
            self.drag_touch = touch_id
            self.drag_global_origin = global_position or QPointF(self.mapToGlobal(position.toPoint()))
            self.drag_window_origin = QPointF(self.pos())
            return
        self.router.move(touch_id, self.key_at(position))

    def _drag_to(self, global_position: QPointF) -> None:
        if self.drag_global_origin is None or self.drag_window_origin is None:
            return
        delta = global_position - self.drag_global_origin
        self.move(
            int(self.drag_window_origin.x() + delta.x()),
            int(self.drag_window_origin.y() + delta.y()),
        )

    def _touch_release(self, touch_id: int, position: QPointF) -> None:
        if self.drag_touch == touch_id:
            self.drag_touch = None
            self.drag_global_origin = None
            self.drag_window_origin = None
            return
        button = self.header_touches.pop(touch_id, None)
        if button is not None:
            button.setDown(False)
            if button.rect().contains(button.mapFrom(self, position.toPoint())):
                button.click()
            return
        self.router.release(touch_id)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self.drag_at(event.position()):
            self.drag_mouse = True
            self.drag_global_origin = event.globalPosition()
            self.drag_window_origin = QPointF(self.pos())
            return
        self.router.move(MOUSE_ID, self.key_at(event.position()))
        self.refresh()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            if self.drag_mouse:
                self._drag_to(event.globalPosition())
            else:
                self.router.move(MOUSE_ID, self.key_at(event.position()))
            self.refresh()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self.drag_mouse:
                self.drag_mouse = False
                self.drag_global_origin = None
                self.drag_window_origin = None
            else:
                self.router.release(MOUSE_ID)
            self.refresh()

    def on_tick(self) -> None:
        self.state.tick()
        self.refresh()

    def external_key(self, code: int, value: int) -> None:
        if value == 0:
            self.external_down.discard(code)
        else:
            self.external_down.add(code)
            if code == CAPS_CODE and value == 1:
                self.external_caps = not self.external_caps
        self.refresh()

    def set_external_caps(self, on: bool) -> None:
        self.external_caps = bool(on)
        self.refresh()

    def refresh(self) -> None:
        shift = self.state.shifted() or bool(self.external_down & {42, 54})
        caps = self.state.caps or self.external_caps
        for widget in self.keys:
            code = widget.key.evdev
            external = code in self.external_down
            widget.set_state(
                self.layout_data.label(widget.key, self.lang, shift, caps),
                code in self.state.down_keys or self.state.mod_state(code) == MOD_PRESSED or external,
                self.state.lit(code)
                or (external and code in self.layout_data.modifier_codes)
                or (code == CAPS_CODE and caps),
                self.state.locked(code),
            )
        self.update_status()

    def update_status(self) -> None:
        event = self.state.last_event
        if event is None:
            suffix = f" · {self.notice}" if self.notice else ""
            self.status.setText(f"{self.backend.name} · layout only{suffix}")
            return
        code, value = event
        key = next((k for k in self.layout_data.keys if k.evdev == code), None)
        name = self.layout_data.label(key, self.lang, False, False) if key else str(code)
        phase = {0: "up", 1: "down", 2: "repeat"}.get(value, str(value))
        self.status.setText(f"{name} ({code}) {phase} · {self.backend.name}")

    def release_all(self) -> None:
        self.router.cancel_all()
        for button in self.header_touches.values():
            button.setDown(False)
        self.header_touches.clear()
        self.drag_touch = None
        self.drag_mouse = False
        self.drag_global_origin = None
        self.drag_window_origin = None
        self.refresh()

    def cancel_touches(self) -> None:
        self.release_all()

    def set_modifier_mode(self, mode: str) -> None:
        if mode not in ("hybrid", "hold", "sticky") or mode == self.modifier_mode:
            return
        self.modifier_mode = mode
        self.state.set_mode(mode)

    def set_track_keyboard(self, enabled: bool) -> None:
        self.track_keyboard_enabled = bool(enabled)
        callback = self.on_track_keyboard
        if callback is not None:
            callback(self.track_keyboard_enabled)

    def clear_external_input(self) -> None:
        self.external_down.clear()
        self.external_caps = False
        self.refresh()

    def _start_candidates(self) -> tuple[bool, str]:
        if self._candidate_controller is not None:
            return True, ""
        try:
            from osk.platform.kimpanel import KimpanelController

            controller = KimpanelController(self)
            ok, error = controller.start()
        except Exception as exc:
            ok, error = False, str(exc)
            controller = None
        if not ok:
            if controller is not None:
                controller.stop()
            self.candidates_error = error
            self.candidate_bar.set_reserved(False)
            self.candidate_bar.clear()
            return False, error
        self._candidate_controller = controller
        self.candidates_enabled = True
        self.candidates_error = ""
        self.candidate_bar.set_reserved(True)
        return True, ""

    def set_candidates_enabled(self, enabled: bool) -> tuple[bool, str]:
        if enabled:
            self.candidates_requested = True
            if not self.isVisible():
                return True, ""
            ok, error = self._start_candidates()
            if not ok:
                self.candidates_requested = False
            return ok, error
        self.candidates_requested = False
        self.stop_candidates()
        return True, ""

    def stop_candidates(self) -> None:
        controller = self._candidate_controller
        if controller is not None:
            controller.stop()
            self._candidate_controller = None
        self.candidates_enabled = False
        self.candidate_bar.set_reserved(False)
        self.candidate_bar.clear()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.candidates_requested and self._candidate_controller is None:
            ok, error = self._start_candidates()
            if not ok:
                self.candidates_requested = False
                print(f"touch-keyboard: {error}", file=__import__("sys").stderr)
        self.visibility_changed.emit(True)

    def hideEvent(self, event) -> None:
        self.release_all()
        if self._candidate_controller is not None:
            self._candidate_controller.stop()
            self._candidate_controller = None
            self.candidates_enabled = False
            self.candidate_bar.set_reserved(False)
            self.candidate_bar.clear()
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.stop_candidates()
        self.release_all()
        self.backend.close()
        event.accept()
        QApplication.instance().quit()
