from __future__ import annotations

import os

from PySide6.QtWidgets import QApplication, QWidget


def _x11() -> bool:
    return QApplication.platformName() in ("xcb", "x11")


def compositor_active() -> bool:
    if os.name == "nt":
        return True
    if not _x11():
        return True
    try:
        from Xlib import display
    except ImportError:
        return True
    try:
        connection = display.Display()
        atom = connection.intern_atom("_NET_WM_CM_S0")
        owner = connection.get_selection_owner(atom)
        connection.close()
        return bool(owner)
    except Exception:
        return True


def _windows_acrylic(window: QWidget) -> bool:
    try:
        import ctypes

        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        setter = user32.SetWindowCompositionAttribute
        setter.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA),
        ]
        setter.restype = ctypes.c_int
        accent = ACCENTPOLICY(4, 2, 0x40000000, 0)
        data = WINDOWCOMPOSITIONATTRIBDATA(
            19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent)
        )
        return bool(setter(int(window.winId()), ctypes.byref(data)))
    except Exception:
        return False


def request_blur(window: QWidget) -> bool:
    if os.name == "nt":
        return _windows_acrylic(window)
    if not _x11():
        return False
    try:
        from Xlib import Xatom, display
    except ImportError:
        return False
    try:
        connection = display.Display()
        target = connection.create_resource_object("window", int(window.winId()))
        region = connection.intern_atom("_KDE_NET_WM_BLUR_BEHIND_REGION")
        target.change_property(
            region,
            Xatom.CARDINAL,
            32,
            [0, 0, max(1, window.width()), max(1, window.height())],
        )
        target.change_property(
            connection.intern_atom("_NET_WM_BLUR_BEHIND"),
            Xatom.CARDINAL,
            32,
            [1],
        )
        connection.sync()
        connection.close()
        return True
    except Exception:
        return False
