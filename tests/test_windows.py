import ctypes

import pytest

from osk.backends.base import DryRunBackend
from osk.backends.windows import INPUT, WINDOWS_SCANCODES, WindowsBackend, open_backend
from osk.core.layout import load_layout
from osk.platform.windows_monitor import WINDOWS_VK, readable_keyboards


def test_every_layout_key_has_a_scan_and_vk_mapping():
    layout = load_layout()
    codes = {key.evdev for key in layout.keys}
    assert codes <= set(WINDOWS_SCANCODES)
    assert codes <= set(WINDOWS_VK)


def test_special_scan_codes_are_extended():
    assert WINDOWS_SCANCODES[1] == (0x01, False)
    assert WINDOWS_SCANCODES[57] == (0x39, False)
    assert WINDOWS_SCANCODES[100] == (0x38, True)
    assert WINDOWS_SCANCODES[103] == (0x48, True)
    assert WINDOWS_SCANCODES[125] == (0x5B, True)


def test_input_struct_matches_windows_abi():
    assert ctypes.sizeof(INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


def test_windows_backend_is_unavailable_elsewhere():
    if __import__("os").name == "nt":
        pytest.skip("running on Windows")
    with pytest.raises(RuntimeError):
        WindowsBackend()
    backend = open_backend()
    assert isinstance(backend, DryRunBackend)


def test_windows_monitor_is_unavailable_elsewhere():
    if __import__("os").name == "nt":
        pytest.skip("running on Windows")
    assert readable_keyboards() == []
