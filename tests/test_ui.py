import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QSize
from PySide6.QtWidgets import QApplication

from osk.backends.base import DryRunBackend
from osk.core.layout import load_layout
from osk.core.state import KeyboardState
from osk.ui.qt import KeyboardWindow, MOUSE_ID


def make_window():
    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    backend = DryRunBackend()
    state = KeyboardState(layout.modifier_codes, backend.key)
    window = KeyboardWindow(layout, state, backend)
    window.resize(1200, 450)
    window.show()
    app.processEvents()
    return window, backend


def center(window, widget):
    return QPointF(widget.mapTo(window, widget.rect().center()))


def key_widget(window, code):
    return next(widget for widget in window.keys if widget.key.evdev == code)


def test_two_finger_shift_and_letter():
    window, backend = make_window()
    shift = key_widget(window, 42)
    letter = key_widget(window, 30)

    window._touch_move(1, center(window, shift), QSize(0, 0))
    window._touch_release(1, center(window, shift))
    window._touch_move(2, center(window, letter), QSize(0, 0))
    window._touch_release(2, center(window, letter))

    assert backend.events == [(42, 1), (30, 1), (30, 0), (42, 0)]


def test_slide_releases_previous_key():
    window, backend = make_window()
    first = key_widget(window, 30)
    second = key_widget(window, 31)

    window._touch_move(1, center(window, first), QSize(0, 0))
    window._touch_move(1, center(window, second), QSize(0, 0))
    window._touch_release(1, center(window, second))

    assert backend.events == [(30, 1), (30, 0), (31, 1), (31, 0)]


def test_mouse_fallback():
    window, backend = make_window()
    window.router.move(MOUSE_ID, 30)
    window.router.release(MOUSE_ID)
    assert backend.events == [(30, 1), (30, 0)]


def test_fn_row_can_start_hidden():
    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    state = KeyboardState(layout.modifier_codes, lambda code, value: None)
    window = KeyboardWindow(layout, state, DryRunBackend(), fn_visible=False)
    window.resize(1200, 450)
    window.show()
    app.processEvents()
    assert not window.row_widgets[0].isVisible()


def test_header_drag_moves_window():
    from PySide6.QtCore import QPoint

    window, _ = make_window()
    window.move(100, 100)
    start = center(window, window.title)
    origin = window.mapToGlobal(start.toPoint())
    window._touch_move(9, start, QSize(0, 0), QPointF(origin))
    window._touch_move(9, start, QSize(0, 0), QPointF(origin.x() + 30, origin.y() + 20))
    window._touch_release(9, start)
    assert window.pos() == QPoint(130, 120)


def test_opacity_is_translucent_and_settable():
    from PySide6.QtCore import Qt

    window, _ = make_window()
    assert window.testAttribute(Qt.WA_TranslucentBackground)
    assert window.opacity_percent == 70
    image = window.grab().toImage()
    assert image.pixelColor(2, 2).alpha() == round(70 * 255 / 100)

    window.set_opacity(5)
    assert window.opacity_percent == 20
    assert window.grab().toImage().pixelColor(2, 2).alpha() == round(20 * 255 / 100)

    window.set_opacity(55)
    assert window.grab().toImage().pixelColor(2, 2).alpha() == round(55 * 255 / 100)

    window.set_opacity(100)
    assert window.grab().toImage().pixelColor(2, 2).alpha() == 255


def test_super_key_taps_and_releases_from_the_window():
    from osk.core.state import SUPER_CODE

    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    backend = DryRunBackend()
    clock = [0.0]
    state = KeyboardState(layout.modifier_codes, backend.key, now=lambda: clock[0])
    window = KeyboardWindow(layout, state, backend)
    window.resize(1200, 450)
    window.show()
    app.processEvents()
    super_key = key_widget(window, SUPER_CODE)

    window._touch_move(1, center(window, super_key), QSize(0, 0))
    clock[0] = 0.05
    window._touch_release(1, center(window, super_key))
    assert backend.events == [(SUPER_CODE, 1)]

    clock[0] = 0.60
    state.tick()
    window.refresh()
    assert backend.events == [(SUPER_CODE, 1), (SUPER_CODE, 0)]
    assert not super_key.lit


def test_key_glow_fades_in_and_out():
    import time

    from PySide6.QtTest import QTest

    from osk.ui.qt import KeyWidget

    def wait_until(widget, predicate, timeout=1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            QTest.qWait(20)
            if predicate(widget.glow()):
                return
        raise AssertionError(f"glow stuck at {widget.glow()}")

    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    key = next(key for key in layout.keys if key.evdev == 30)
    widget = KeyWidget(key)
    widget.resize(80, 40)
    widget.show()
    assert widget.glow() == 0.0

    widget.set_state("a", True, False, False)
    wait_until(widget, lambda value: value > 0.98)

    widget.set_state("a", False, False, False)
    wait_until(widget, lambda value: value < 0.02)

    widget.set_state("a", False, True, False)
    wait_until(widget, lambda value: abs(value - KeyWidget.GLOW_LIT) < 0.02)
    app.processEvents()


def test_physical_keyboard_highlights_and_shifts_labels():
    from osk.core.state import CAPS_CODE

    window, _ = make_window()
    shift = key_widget(window, 42)
    letter = key_widget(window, 30)

    window.external_key(42, 1)
    assert shift.pressed and shift.lit
    assert letter.label == "A"
    window.external_key(30, 1)
    assert letter.pressed
    assert letter.label == "A"
    window.external_key(30, 0)
    assert not letter.pressed
    window.external_key(42, 0)
    assert not shift.pressed and not shift.lit
    assert letter.label == "a"

    window.external_key(CAPS_CODE, 1)
    window.external_key(CAPS_CODE, 0)
    assert window.external_caps
    assert letter.label == "A"
    window.external_key(CAPS_CODE, 1)
    window.external_key(CAPS_CODE, 0)
    assert not window.external_caps
    assert letter.label == "a"


def test_external_caps_can_be_seeded_from_led_state():
    window, _ = make_window()
    letter = key_widget(window, 30)
    window.set_external_caps(True)
    assert letter.label == "A"
    window.set_external_caps(False)
    assert letter.label == "a"


def test_minimize_to_tray_and_close_without_tray(monkeypatch):
    window, _ = make_window()
    assert window.minimize_button.text() == "Minimize"

    window.tray_available = True
    window.minimize()
    assert not window.isVisible()

    window.show()
    window.tray_available = False
    closed = []
    monkeypatch.setattr(window, "close", lambda: closed.append(True))
    window.minimize()
    assert closed == [True]

    window.toggle_lang()
    assert window.minimize_button.text() == "最小化"


def test_keyboard_custom_width_percent(monkeypatch):
    from PySide6.QtCore import QRect

    window, _ = make_window()
    monkeypatch.setattr(window, "_available_area", lambda: QRect(0, 0, 1920, 1080))

    window.set_width_percent(60)
    assert window.width() == 1152
    assert window.size_percent() == 60

    window.set_width_percent(30)
    assert window.width() == 640
    assert window.size_percent() == 33
