import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from osk.backends.base import DryRunBackend
from osk.core.layout import load_layout
from osk.core.state import KeyboardState
from osk.platform.tray import Tray
from osk.ui.icon import app_icon
from osk.ui.qt import KeyboardWindow


def make_window():
    app = QApplication.instance() or QApplication([])
    layout = load_layout()
    state = KeyboardState(layout.modifier_codes, lambda code, value: None)
    window = KeyboardWindow(layout, state, DryRunBackend())
    window.show()
    app.processEvents()
    return app, window


def test_icon_is_available():
    QApplication.instance() or QApplication([])
    assert not app_icon().isNull()


def test_tray_toggles_window_and_follows_language():
    app, window = make_window()
    tray = Tray(window, app)
    assert window.isVisible()
    assert "Hide" in tray.toggle_action.text()

    tray.toggle()
    assert not window.isVisible()
    assert "Show" in tray.toggle_action.text()

    tray.toggle()
    assert window.isVisible()
    assert "Hide" in tray.toggle_action.text()

    window.toggle_lang()
    assert tray.toggle_action.text() == "隐藏键盘"
    assert tray.quit_action.text() == "退出"
    tray.hide()


def test_packaged_icon_assets_cover_common_sizes():
    from osk.ui.icon import ASSET_DIR

    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        assert (ASSET_DIR / f"icon-{size}.png").is_file()
    assert (ASSET_DIR / "icon.svg").is_file()
    assert (ASSET_DIR / "icon.ico").is_file()
    icon = app_icon()
    for size in (16, 32, 256):
        assert not icon.pixmap(size).isNull()


def test_tray_size_submenu_has_ten_percent_steps(monkeypatch):
    from PySide6.QtCore import QRect

    app, window = make_window()
    monkeypatch.setattr(window, "_available_area", lambda: QRect(0, 0, 1920, 1080))
    tray = Tray(window, app)
    assert sorted(tray.size_actions) == list(range(30, 101, 10))
    assert tray.size_menu.title() == "Size"

    tray.set_size(60)
    assert window.width() == 1152
    assert tray.size_actions[60].isChecked()
    assert not tray.size_actions[70].isChecked()

    tray.set_size(90)
    assert window.width() == 1728
    assert tray.size_actions[90].isChecked()

    window.toggle_lang()
    assert tray.size_menu.title() == "大小"
    tray.hide()


def test_tray_opacity_submenu_has_ten_percent_steps(monkeypatch):
    app, window = make_window()
    tray = Tray(window, app)
    assert sorted(tray.opacity_actions) == list(range(20, 101, 10))
    assert tray.opacity_menu.title() == "Opacity"

    tray.set_opacity(50)
    assert window.opacity_percent == 50
    assert tray.opacity_actions[50].isChecked()
    assert not tray.opacity_actions[60].isChecked()

    window.toggle_lang()
    assert tray.opacity_menu.title() == "透明度"
    tray.hide()


def test_tray_language_and_fn_row_actions():
    app, window = make_window()
    tray = Tray(window, app)
    assert set(tray.language_actions) == {"en", "zh"}
    assert tray.language_actions["en"].isChecked()

    tray.language_actions["zh"].trigger()
    assert window.lang == "zh"
    assert tray.language_menu.title() == "语言"
    assert tray.language_actions["zh"].isChecked()

    assert tray.fn_action.isChecked()
    assert window.row_widgets[0].isVisible()
    tray.fn_action.trigger()
    assert not window.fn_visible
    assert not window.row_widgets[0].isVisible()
    assert not tray.fn_action.isChecked()

    tray.fn_action.trigger()
    assert window.fn_visible
    assert window.row_widgets[0].isVisible()
    assert tray.fn_action.isChecked()
    tray.hide()


def test_tray_candidate_pin_action():
    app, window = make_window()
    calls = []
    window.set_candidates_enabled = lambda enabled: (calls.append(enabled) or (True, ""))
    tray = Tray(window, app)
    assert tray.candidates_action.isCheckable()
    assert "candidate" in tray.candidates_action.text().lower()

    tray.candidates_action.trigger()
    assert calls == [True]
    window.toggle_lang()
    assert "候选框" in tray.candidates_action.text()
    tray.hide()


def test_tray_modifier_mode_submenu():
    app, window = make_window()
    tray = Tray(window, app)
    assert set(tray.modifier_actions) == {"hybrid", "hold", "sticky"}
    assert tray.modifier_actions["hybrid"].isChecked()

    tray.set_modifier_mode("hold")
    assert window.modifier_mode == "hold"
    assert window.state.mode == "hold"
    assert tray.modifier_actions["hold"].isChecked()
    assert not tray.modifier_actions["hybrid"].isChecked()

    window.toggle_lang()
    assert tray.modifier_menu.title() == "快捷键操作方式"
    assert tray.modifier_actions["sticky"].text() == "粘滞"
    tray.hide()


def test_toggle_keyboard_is_first_menu_item():
    app, window = make_window()
    tray = Tray(window, app)
    assert tray.menu.actions()[0] is tray.toggle_action
    tray.hide()
