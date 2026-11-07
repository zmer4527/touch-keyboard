from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from osk.ui.icon import app_icon


class Tray(QObject):
    def __init__(self, window, app: QApplication):
        super().__init__(window)
        self.window = window
        self.app = app
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.menu = QMenu()
        self.size_menu = self.menu.addMenu("Size")
        self.size_group = QActionGroup(self.menu)
        self.size_group.setExclusive(True)
        self.size_actions: dict[int, QAction] = {}
        for percent in range(30, 101, 10):
            action = QAction(f"{percent}%", self.size_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, value=percent: self.set_size(value))
            self.size_group.addAction(action)
            self.size_menu.addAction(action)
            self.size_actions[percent] = action
        self.opacity_menu = self.menu.addMenu("Opacity")
        self.opacity_group = QActionGroup(self.menu)
        self.opacity_group.setExclusive(True)
        self.opacity_actions: dict[int, QAction] = {}
        for percent in range(20, 101, 10):
            action = QAction(f"{percent}%", self.opacity_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, value=percent: self.set_opacity(value))
            self.opacity_group.addAction(action)
            self.opacity_menu.addAction(action)
            self.opacity_actions[percent] = action
        self.language_menu = self.menu.addMenu("Language")
        self.language_group = QActionGroup(self.menu)
        self.language_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for code, label in (("en", "English"), ("zh", "中文")):
            action = QAction(label, self.language_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, value=code: self.set_language(value))
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[code] = action
        self.modifier_menu = self.menu.addMenu("Modifier keys")
        self.modifier_group = QActionGroup(self.menu)
        self.modifier_group.setExclusive(True)
        self.modifier_actions: dict[str, QAction] = {}
        for code, label in (
            ("hybrid", "Hybrid"),
            ("hold", "Hold"),
            ("sticky", "Sticky"),
        ):
            action = QAction(label, self.modifier_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, value=code: self.set_modifier_mode(value))
            self.modifier_group.addAction(action)
            self.modifier_menu.addAction(action)
            self.modifier_actions[code] = action
        self.fn_action = QAction(self.menu)
        self.fn_action.setCheckable(True)
        self.fn_action.triggered.connect(self.set_fn_visible)
        self.menu.addAction(self.fn_action)
        self.candidates_action = QAction(self.menu)
        self.candidates_action.setCheckable(True)
        self.candidates_action.triggered.connect(self.set_candidates)
        self.menu.addAction(self.candidates_action)
        self.toggle_action = QAction(self.menu)
        self.quit_action = QAction(self.menu)
        self.toggle_action.triggered.connect(self.toggle)
        self.quit_action.triggered.connect(self.window.close)
        self.menu.addAction(self.toggle_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.menu.removeAction(self.toggle_action)
        self.menu.insertAction(self.menu.actions()[0], self.toggle_action)
        self.menu.aboutToShow.connect(self.refresh)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.window.language_changed.connect(self.refresh)
        self.window.visibility_changed.connect(self.refresh)
        self.refresh()
        self.icon.show()

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle()

    def set_size(self, percent: int) -> None:
        self.window.set_width_percent(percent)
        self.refresh()

    def set_opacity(self, percent: int) -> None:
        self.window.set_opacity(percent)
        self.refresh()

    def set_language(self, lang: str) -> None:
        self.window.set_language(lang)
        self.refresh()

    def set_modifier_mode(self, mode: str) -> None:
        self.window.set_modifier_mode(mode)
        self.refresh()

    def set_fn_visible(self, visible: bool) -> None:
        self.window.set_fn_visible(visible)
        self.refresh()

    def set_candidates(self, enabled: bool) -> None:
        ok, error = self.window.set_candidates_enabled(enabled)
        if not ok:
            self.icon.showMessage("Touch Keyboard", error, QSystemTrayIcon.MessageIcon.Warning, 5000)
        self.refresh()

    def toggle(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show()
            self.window.raise_()
        self.refresh()

    def refresh(self, *_) -> None:
        zh = self.window.lang == "zh"
        visible = self.window.isVisible()
        if visible:
            self.toggle_action.setText("隐藏键盘" if zh else "Hide keyboard")
        else:
            self.toggle_action.setText("显示键盘" if zh else "Show keyboard")
        self.size_menu.setTitle("大小" if zh else "Size")
        current = self.window.size_percent()
        nearest = min(self.size_actions, key=lambda percent: abs(percent - current))
        self.size_actions[nearest].setChecked(True)
        self.opacity_menu.setTitle("透明度" if zh else "Opacity")
        current_opacity = self.window.opacity_percent
        nearest_opacity = min(self.opacity_actions, key=lambda percent: abs(percent - current_opacity))
        self.opacity_actions[nearest_opacity].setChecked(True)
        self.language_menu.setTitle("语言" if zh else "Language")
        self.language_actions[self.window.lang].setChecked(True)
        self.modifier_menu.setTitle("快捷键操作方式" if zh else "Modifier keys")
        for code, text in (("hybrid", "混合"), ("hold", "长按"), ("sticky", "粘滞")):
            self.modifier_actions[code].setText(text if zh else code.capitalize())
        self.modifier_actions[self.window.modifier_mode].setChecked(True)
        self.fn_action.setText("F1-F12 功能" if zh else "F1-F12 row")
        self.fn_action.setChecked(self.window.fn_visible)
        self.candidates_action.setText("候选框固定到键盘上方" if zh else "Pin IME candidates above keyboard")
        self.candidates_action.setChecked(self.window.candidates_requested)
        self.quit_action.setText("退出" if zh else "Quit")
        self.icon.setToolTip("触摸键盘" if zh else "Touch keyboard")

    def hide(self) -> None:
        self.icon.hide()
