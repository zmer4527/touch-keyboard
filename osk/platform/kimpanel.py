from __future__ import annotations

import os
import re
import shutil
import subprocess

from PySide6.QtCore import QObject, QTimer, SLOT, Slot
from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusVirtualObject

PANEL_SERVICE = "org.kde.impanel"
PANEL_PATH = "/org/kde/impanel"
KIMPANEL_SERVICE = "org.kde.kimpanel.inputmethod"
KIMPANEL_PATH = "/kimpanel"
FCITX_SERVICE = "org.fcitx.Fcitx5"
FCITX_CONTROLLER_PATH = "/controller"
FCITX_CONTROLLER_IFACE = "org.fcitx.Fcitx.Controller1"

PANEL_XML = """<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN" "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
<node>
 <interface name="org.kde.impanel2">
  <method name="SetLookupTable">
   <arg name="labels" type="as" direction="in"/>
   <arg name="texts" type="as" direction="in"/>
   <arg name="attrs" type="as" direction="in"/>
   <arg name="hasPrev" type="b" direction="in"/>
   <arg name="hasNext" type="b" direction="in"/>
   <arg name="cursor" type="i" direction="in"/>
   <arg name="layout" type="i" direction="in"/>
  </method>
  <method name="SetSpotRect"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="SetRelativeSpotRect"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <method name="SetRelativeSpotRectV2"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
  <signal name="PanelCreated2"/>
 </interface>
 <interface name="org.kde.impanel">
  <signal name="SelectCandidate"><arg type="i"/></signal>
  <signal name="LookupTablePageUp"/>
  <signal name="LookupTablePageDown"/>
  <signal name="PanelCreated"/>
  <signal name="TriggerProperty"><arg type="s"/></signal>
 </interface>
</node>"""


def _addon_enabled(name: str) -> bool | None:
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                FCITX_SERVICE,
                "--object-path",
                FCITX_CONTROLLER_PATH,
                "--method",
                f"{FCITX_CONTROLLER_IFACE}.GetAddons",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    match = re.search(
        r"\('" + re.escape(name) + r"',\s*'(?:[^'\\]|\\.)*',\s*'(?:[^'\\]|\\.)*',\s*\d+,\s*(true|false)",
        result.stdout,
    )
    return match.group(1) == "true" if match else None


def _set_addons(states: dict[str, bool]) -> bool:
    text = "[" + ", ".join(
        f"('{name}', {'true' if value else 'false'})" for name, value in states.items()
    ) + "]"
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                FCITX_SERVICE,
                "--object-path",
                FCITX_CONTROLLER_PATH,
                "--method",
                f"{FCITX_CONTROLLER_IFACE}.SetAddonsState",
                text,
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def restore_classicui() -> bool:
    return _set_addons({"classicui": True})


def _kde_wayland() -> bool:
    desktop = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        + " "
        + os.environ.get("XDG_SESSION_DESKTOP", "")
    ).upper()
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or os.environ.get(
        "XDG_SESSION_TYPE"
    ) == "wayland"
    return wayland and ("KDE" in desktop or "PLASMA" in desktop)


class _PanelObject(QDBusVirtualObject):
    def __init__(self, controller: "KimpanelController"):
        super().__init__()
        self.controller = controller

    def introspect(self, path: str) -> str:
        return PANEL_XML

    def handleMessage(self, message, connection) -> bool:
        interface = message.interface()
        member = message.member()
        if interface == "org.freedesktop.DBus.Introspectable" and member == "Introspect":
            connection.send(message.createReply(PANEL_XML))
            return True
        if interface == "org.kde.impanel2" and member == "SetLookupTable":
            arguments = message.arguments()
            if len(arguments) >= 7:
                labels, texts, _attrs, has_prev, has_next, cursor, _layout = arguments[:7]
                self.controller.update_lookup(labels, texts, has_prev, has_next, cursor)
            connection.send(message.createReply())
            return True
        if interface == "org.kde.impanel2" and member.startswith("Set"):
            connection.send(message.createReply())
            return True
        return False


class KimpanelController(QObject):
    def __init__(self, keyboard):
        super().__init__()
        self.keyboard = keyboard
        self.bus = QDBusConnection.sessionBus()
        self.bar = keyboard.candidate_bar
        self.bar.selected.connect(self._select)
        self.bar.page_up.connect(self._page_up)
        self.bar.page_down.connect(self._page_down)
        self.object = None
        self.started = False
        self._active = True
        self._connected = False
        self._connections: list[tuple[str, str]] = []
        self._retries = 0
        self._classicui_before: bool | None = None
        self._kimpanel_before: bool | None = None
        self._changed_classicui = False
        self._changed_kimpanel = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._connect_signals)

    def start(self) -> tuple[bool, str]:
        if self.started:
            return True, ""
        if not self.bus.isConnected():
            return False, "D-Bus session bus is not available"
        if not shutil.which("gdbus"):
            return False, "gdbus is required for Fcitx candidate pinning"
        if self.bus.registerService(PANEL_SERVICE) is False:
            return False, "another Kimpanel panel is already registered"
        self.object = _PanelObject(self)
        if not self.bus.registerVirtualObject(
            PANEL_PATH, self.object, QDBusConnection.VirtualObjectRegisterOption.SingleNode
        ):
            self.bus.unregisterService(PANEL_SERVICE)
            self.object = None
            return False, "failed to register the Kimpanel object"

        self.started = True
        self._classicui_before = _addon_enabled("classicui")
        self._kimpanel_before = _addon_enabled("kimpanel")
        states = {"kimpanel": True}
        self._changed_kimpanel = self._kimpanel_before is not True
        if _kde_wayland():
            states["classicui"] = False
            self._changed_classicui = self._classicui_before is not False
        if not _set_addons(states):
            self.stop()
            return False, "failed to enable the Fcitx Kimpanel addon"

        self._send("PanelCreated")
        self._panel_signal("PanelCreated2")
        self._timer.start(120)
        return True, ""

    def stop(self) -> None:
        self._active = False
        self._timer.stop()
        for name, signature in self._connections:
            self.bus.disconnect(
                KIMPANEL_SERVICE,
                KIMPANEL_PATH,
                KIMPANEL_SERVICE,
                name,
                self,
                SLOT(signature),
            )
        self._connections.clear()
        if self.bar is not None:
            for signal, slot in (
                (self.bar.selected, self._select),
                (self.bar.page_up, self._page_up),
                (self.bar.page_down, self._page_down),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
            self.bar.clear()
        self.bar = None
        if self.started:
            self.bus.unregisterObject(PANEL_PATH)
            self.bus.unregisterService(PANEL_SERVICE)
        self.object = None
        self.started = False
        restore = {}
        if self._changed_classicui:
            restore["classicui"] = True if self._classicui_before is None else self._classicui_before
        if self._changed_kimpanel:
            restore["kimpanel"] = False if self._kimpanel_before is False else True
        if restore:
            _set_addons(restore)
        self._changed_classicui = False
        self._changed_kimpanel = False

    def _connect_signals(self) -> None:
        if not self._active:
            return
        signals = {
            "UpdatePreeditText": "update_preedit(QString,QString)",
            "UpdateAux": "update_aux(QString,QString)",
            "ShowPreedit": "show_preedit(bool)",
            "ShowAux": "show_aux(bool)",
            "ShowLookupTable": "show_lookup(bool)",
            "UpdatePreeditCaret": "update_caret(int)",
            "UpdateLookupTableCursor": "update_cursor(int)",
            "UpdateProperty": "update_property(QString)",
            "RemoveProperty": "remove_property(QString)",
            "RegisterProperties": "register_properties(QStringList)",
            "Enable": "enable(bool)",
            "UpdateSpotLocation": "update_spot(int,int)",
            "UpdateScreen": "update_screen(int)",
        }
        connected = 0
        for name, signature in signals.items():
            if self.bus.connect(
                KIMPANEL_SERVICE,
                KIMPANEL_PATH,
                KIMPANEL_SERVICE,
                name,
                self,
                SLOT(signature),
            ):
                connected += 1
                self._connections.append((name, signature))
        if connected:
            self._connected = True
        elif self._retries < 10 and self.started:
            self._retries += 1
            self._timer.start(150)
        self._retries = 0 if connected else self._retries

    def _send(self, name: str, *arguments) -> None:
        if not self._active:
            return
        message = QDBusMessage.createSignal(PANEL_PATH, "org.kde.impanel", name)
        for argument in arguments:
            message << argument
        self.bus.send(message)

    def _panel_signal(self, name: str) -> None:
        if not self._active:
            return
        message = QDBusMessage.createSignal(PANEL_PATH, "org.kde.impanel2", name)
        self.bus.send(message)

    def _select(self, index: int) -> None:
        self._send("SelectCandidate", int(index))

    def _page_up(self) -> None:
        self._send("LookupTablePageUp")

    def _page_down(self) -> None:
        self._send("LookupTablePageDown")

    def update_lookup(self, labels, texts, has_prev, has_next, cursor) -> None:
        if self.bar is None:
            return
        self.bar.set_lookup(
            [str(value) for value in labels],
            [str(value) for value in texts],
            bool(has_prev),
            bool(has_next),
            int(cursor),
        )

    @Slot(bool)
    def show_lookup(self, visible: bool) -> None:
        if self.bar is not None:
            self.bar.set_lookup_visible(visible)

    @Slot(bool)
    def show_preedit(self, visible: bool) -> None:
        if self.bar is not None:
            self.bar.set_preedit_visible(visible)

    @Slot(str, str)
    def update_preedit(self, text: str, _attributes: str) -> None:
        if self.bar is not None:
            self.bar.set_preedit(text)

    @Slot(str, str)
    def update_aux(self, _text: str, _attributes: str) -> None:
        pass

    @Slot(bool)
    def show_aux(self, _visible: bool) -> None:
        pass

    @Slot(int)
    def update_caret(self, _caret: int) -> None:
        pass

    @Slot(int)
    def update_cursor(self, cursor: int) -> None:
        if self.bar is not None:
            self.bar.set_cursor(cursor)

    @Slot(str)
    def update_property(self, _property: str) -> None:
        pass

    @Slot(str)
    def remove_property(self, _property: str) -> None:
        pass

    @Slot("QStringList")
    def register_properties(self, _properties) -> None:
        pass

    @Slot(bool)
    def enable(self, _enabled: bool) -> None:
        pass

    @Slot(int, int)
    def update_spot(self, _x: int, _y: int) -> None:
        pass

    @Slot(int)
    def update_screen(self, _screen: int) -> None:
        pass
