from __future__ import annotations

import ctypes
import os

from osk.backends.base import DryRunBackend, KeyBackend

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

WORD = ctypes.c_ushort
DWORD = ctypes.c_uint32
LONG = ctypes.c_int32
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", DWORD),
        ("u", _INPUTUNION),
    ]


WINDOWS_SCANCODES: dict[int, tuple[int, bool]] = {
    1: (0x01, False),
    2: (0x02, False),
    3: (0x03, False),
    4: (0x04, False),
    5: (0x05, False),
    6: (0x06, False),
    7: (0x07, False),
    8: (0x08, False),
    9: (0x09, False),
    10: (0x0A, False),
    11: (0x0B, False),
    12: (0x0C, False),
    13: (0x0D, False),
    14: (0x0E, False),
    15: (0x0F, False),
    16: (0x10, False),
    17: (0x11, False),
    18: (0x12, False),
    19: (0x13, False),
    20: (0x14, False),
    21: (0x15, False),
    22: (0x16, False),
    23: (0x17, False),
    24: (0x18, False),
    25: (0x19, False),
    26: (0x1A, False),
    27: (0x1B, False),
    28: (0x1C, False),
    29: (0x1D, False),
    30: (0x1E, False),
    31: (0x1F, False),
    32: (0x20, False),
    33: (0x21, False),
    34: (0x22, False),
    35: (0x23, False),
    36: (0x24, False),
    37: (0x25, False),
    38: (0x26, False),
    39: (0x27, False),
    40: (0x28, False),
    41: (0x29, False),
    42: (0x2A, False),
    43: (0x2B, False),
    44: (0x2C, False),
    45: (0x2D, False),
    46: (0x2E, False),
    47: (0x2F, False),
    48: (0x30, False),
    49: (0x31, False),
    50: (0x32, False),
    51: (0x33, False),
    52: (0x34, False),
    53: (0x35, False),
    54: (0x36, False),
    56: (0x38, False),
    57: (0x39, False),
    58: (0x3A, False),
    59: (0x3B, False),
    60: (0x3C, False),
    61: (0x3D, False),
    62: (0x3E, False),
    63: (0x3F, False),
    64: (0x40, False),
    65: (0x41, False),
    66: (0x42, False),
    67: (0x43, False),
    68: (0x44, False),
    87: (0x57, False),
    88: (0x58, False),
    97: (0x1D, True),
    100: (0x38, True),
    102: (0x47, True),
    103: (0x48, True),
    104: (0x49, True),
    105: (0x4B, True),
    106: (0x4D, True),
    107: (0x4F, True),
    108: (0x50, True),
    109: (0x51, True),
    110: (0x52, True),
    111: (0x53, True),
    125: (0x5B, True),
}


class WindowsBackend(KeyBackend):
    name = "windows-sendinput"

    def __init__(self):
        if os.name != "nt":
            raise RuntimeError("SendInput is only available on Windows")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [DWORD, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = DWORD

    def key(self, code: int, value: int) -> None:
        mapping = WINDOWS_SCANCODES.get(code)
        if mapping is None:
            return
        scan, extended = mapping
        flags = KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if value == 0:
            flags |= KEYEVENTF_KEYUP
        event = INPUT()
        event.type = INPUT_KEYBOARD
        event.ki = KEYBDINPUT(0, scan, flags, 0, 0)
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) != 1:
            raise OSError(ctypes.get_last_error(), "SendInput failed")


def open_backend(force_dry_run: bool = False) -> KeyBackend:
    if force_dry_run:
        return DryRunBackend("forced dry run")
    try:
        return WindowsBackend()
    except Exception as exc:
        return DryRunBackend(str(exc))
