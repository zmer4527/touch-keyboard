from __future__ import annotations

import ctypes
import os
import threading

from PySide6.QtCore import QObject, Signal

VK_CAPITAL = 0x14

WINDOWS_VK: dict[int, int] = {
    1: 0x1B,
    2: 0x31,
    3: 0x32,
    4: 0x33,
    5: 0x34,
    6: 0x35,
    7: 0x36,
    8: 0x37,
    9: 0x38,
    10: 0x39,
    11: 0x30,
    12: 0xBD,
    13: 0xBB,
    14: 0x08,
    15: 0x09,
    16: 0x51,
    17: 0x57,
    18: 0x45,
    19: 0x52,
    20: 0x54,
    21: 0x59,
    22: 0x55,
    23: 0x49,
    24: 0x4F,
    25: 0x50,
    26: 0xDB,
    27: 0xDD,
    28: 0x0D,
    29: 0xA2,
    30: 0x41,
    31: 0x53,
    32: 0x44,
    33: 0x46,
    34: 0x47,
    35: 0x48,
    36: 0x4A,
    37: 0x4B,
    38: 0x4C,
    39: 0xBA,
    40: 0xDE,
    41: 0xC0,
    42: 0xA0,
    43: 0xDC,
    44: 0x5A,
    45: 0x58,
    46: 0x43,
    47: 0x56,
    48: 0x42,
    49: 0x4E,
    50: 0x4D,
    51: 0xBC,
    52: 0xBE,
    53: 0xBF,
    54: 0xA1,
    56: 0xA4,
    57: 0x20,
    58: 0x14,
    59: 0x70,
    60: 0x71,
    61: 0x72,
    62: 0x73,
    63: 0x74,
    64: 0x75,
    65: 0x76,
    66: 0x77,
    67: 0x78,
    68: 0x79,
    87: 0x7A,
    88: 0x7B,
    97: 0xA3,
    100: 0xA5,
    102: 0x24,
    103: 0x26,
    104: 0x21,
    105: 0x25,
    106: 0x27,
    107: 0x23,
    108: 0x28,
    109: 0x22,
    110: 0x2D,
    111: 0x2E,
    125: 0x5B,
}


def readable_keyboards(paths: list[str] | None = None) -> list[tuple[str, str]]:
    if os.name == "nt":
        return [("windows", "polling")]
    return []


class KeyboardMonitor(QObject):
    key = Signal(int, int)
    caps = Signal(bool)
    status = Signal(str)

    def __init__(self, devices: list[str] | None = None):
        super().__init__()
        self.devices = devices
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if os.name != "nt":
            self.status.emit("physical keyboard tracking is only available on Windows")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="osk-win32", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = ctypes.c_short
        except Exception as exc:
            self.status.emit(f"physical keyboard tracking unavailable: {exc}")
            return

        self.status.emit("tracking physical keyboard (Windows)")
        down: set[int] = set()
        caps: bool | None = None
        while not self._stop.wait(0.016):
            pressed = {
                code
                for code, vk in WINDOWS_VK.items()
                if user32.GetAsyncKeyState(vk) & 0x8000
            }
            for code in pressed - down:
                self.key.emit(code, 1)
            for code in down - pressed:
                self.key.emit(code, 0)
            down = pressed

            state = bool(user32.GetAsyncKeyState(VK_CAPITAL) & 0x0001)
            if state != caps:
                caps = state
                self.caps.emit(state)


WindowsKeyboardMonitor = KeyboardMonitor
