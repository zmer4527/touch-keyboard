from osk.core.layout import load_layout


def test_default_layout_shape():
    layout = load_layout()
    assert len(layout.rows) == 6
    assert len(layout.keys) == 82
    assert 42 in layout.modifier_codes
    assert layout.rows[0][0].evdev == 1


def test_shifted_and_caps_labels():
    layout = load_layout()
    key = next(key for key in layout.keys if key.evdev == 30)
    assert layout.label(key, "en") == "a"
    assert layout.label(key, "en", shift=True) == "A"
    assert layout.label(key, "en", caps=True) == "A"
    assert layout.label(key, "en", shift=True, caps=True) == "a"

    comma = next(key for key in layout.keys if key.evdev == 51)
    assert layout.label(comma, shift=True) == "<"


def test_localized_labels():
    layout = load_layout()
    space = next(key for key in layout.keys if key.evdev == 57)
    assert layout.title("zh") == "PC 键盘"
    assert layout.label(space, "zh") == "空格"
    assert layout.label(space, "en") == "Space"
