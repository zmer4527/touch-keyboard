import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from osk.backends.base import DryRunBackend
from osk.core.layout import load_layout
from osk.core.state import KeyboardState
from osk.ui.qt import KeyboardWindow


def make_window():
    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    state = KeyboardState(layout.modifier_codes, lambda code, value: None)
    window = KeyboardWindow(layout, state, DryRunBackend())
    window.resize(600, 220)
    window.show()
    app.processEvents()
    return app, window


def test_candidate_bar_is_embedded_and_selects():
    app, window = make_window()
    bar = window.candidate_bar
    seen = []
    bar.selected.connect(seen.append)

    bar.set_lookup(["1.", "2.", ""], ["你", "好", "候选说明"], False, True, 1)
    bar.set_lookup_visible(True)
    app.processEvents()

    assert bar.parent() is window
    assert [button.text() for button in bar.buttons] == ["1. 你", "2. 好"]
    assert bar.buttons[1].property("selected") is True
    assert bar.next_button.isVisible()
    assert not bar.prev_button.isVisible()
    assert bar.isVisible()

    bar.buttons[0].click()
    assert seen == [0]

    bar.set_preedit("ni hao")
    bar.set_preedit_visible(True)
    assert bar.preedit.text() == "ni hao"

    bar.set_lookup_visible(False)
    bar.set_preedit_visible(False)
    assert not bar.isVisible()


def test_candidate_page_buttons_emit():
    app, window = make_window()
    bar = window.candidate_bar
    pages = []
    bar.page_up.connect(lambda: pages.append("up"))
    bar.page_down.connect(lambda: pages.append("down"))
    bar.set_lookup(["1."], ["你"], True, True, 0)
    bar.set_lookup_visible(True)
    app.processEvents()

    bar.prev_button.click()
    bar.next_button.click()
    assert pages == ["up", "down"]


def test_set_lookup_table_dbus_method_updates_bar():
    from PySide6.QtDBus import QDBusMessage

    from osk.platform.kimpanel import _PanelObject, KimpanelController

    app, window = make_window()
    controller = KimpanelController(window)
    panel = _PanelObject(controller)
    message = QDBusMessage.createMethodCall(
        "org.kde.impanel", "/org/kde/impanel", "org.kde.impanel2", "SetLookupTable"
    )
    message << ["1.", "2."] << ["你", "好"] << ["", ""] << False << True << 1 << 0

    class Connection:
        def __init__(self):
            self.sent = []

        def send(self, reply):
            self.sent.append(reply)

    connection = Connection()
    assert panel.handleMessage(message, connection)
    assert connection.sent
    assert [button.text() for button in window.candidate_bar.buttons] == ["1. 你", "2. 好"]


def test_reserved_bar_keeps_keyboard_height_stable():
    app, window = make_window()
    window.resize(1000, 420)
    app.processEvents()
    bar = window.candidate_bar
    bar.set_reserved(True)
    app.processEvents()
    before = (window.height(), window.row_widgets[1].height(), window.row_widgets[5].height())

    bar.set_preedit("nihao")
    bar.set_preedit_visible(True)
    bar.set_lookup(["1.", "2."], ["你", "好"], False, False, 0)
    bar.set_lookup_visible(True)
    app.processEvents()
    during = (window.height(), window.row_widgets[1].height(), window.row_widgets[5].height())

    bar.set_lookup_visible(False)
    bar.set_preedit_visible(False)
    app.processEvents()
    after = (window.height(), window.row_widgets[1].height(), window.row_widgets[5].height())
    assert before == during == after

    bar.set_reserved(False)
