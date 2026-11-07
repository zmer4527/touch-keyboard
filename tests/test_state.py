import pytest

from osk.core.state import KeyboardState, MOD_LOCKED, MOD_OFF, MOD_ONCE, MOD_PRESSED, SUPER_CODE

MODS = {42, 54, 29, 97, 56, 100, 125}
SHIFT = 42
LETTER = 30
CAPS = 58


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def board():
    clock = Clock()
    events = []
    state = KeyboardState(MODS, lambda code, value: events.append((code, value)), now=clock)
    return clock, events, state


def test_shift_tap_is_sticky_once(board):
    clock, events, state = board
    state.key_down(SHIFT)
    clock.t = 0.05
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_ONCE
    assert events == [(SHIFT, 1)]
    assert state.shifted()

    clock.t = 0.10
    state.key_down(LETTER)
    state.key_up(LETTER)
    assert events == [(SHIFT, 1), (LETTER, 1), (LETTER, 0), (SHIFT, 0)]
    assert state.mod_state(SHIFT) == MOD_OFF


def test_shift_hold_is_momentary(board):
    clock, events, state = board
    state.key_down(SHIFT)
    clock.t = 0.30
    assert state.mod_state(SHIFT) == MOD_PRESSED
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_OFF
    assert events == [(SHIFT, 1), (SHIFT, 0)]


def test_shift_taps_lock_and_unlock(board):
    clock, events, state = board
    state.key_down(SHIFT)
    clock.t = 0.05
    state.key_up(SHIFT)
    clock.t = 0.10
    state.key_down(SHIFT)
    clock.t = 0.15
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_LOCKED

    clock.t = 0.20
    state.key_down(LETTER)
    state.key_up(LETTER)
    assert (SHIFT, 0) not in events
    assert state.mod_state(SHIFT) == MOD_LOCKED

    clock.t = 0.30
    state.key_down(SHIFT)
    assert state.mod_state(SHIFT) == MOD_OFF
    assert events[-1] == (SHIFT, 0)


def test_caps_toggles_on_release(board):
    _, events, state = board
    state.key_down(CAPS)
    assert not state.caps
    state.key_up(CAPS)
    assert state.caps and state.lit(CAPS)
    state.key_down(CAPS)
    state.key_up(CAPS)
    assert not state.caps
    assert events == []


def test_repeat_uses_value_two(board):
    clock, events, state = board
    state.key_down(LETTER)
    clock.t = 0.39
    state.tick()
    assert events == [(LETTER, 1)]
    clock.t = 0.40
    state.tick()
    assert events[-1] == (LETTER, 2)
    clock.t = 0.44
    state.tick()
    assert events[-1] == (LETTER, 2)
    state.key_up(LETTER)
    assert events[-1] == (LETTER, 0)
    assert LETTER not in state.down_keys


def test_release_all_clears_modifiers_and_keys(board):
    _, events, state = board
    state.key_down(SHIFT)
    state.key_down(LETTER)
    state.release_all()
    assert state.mods == {}
    assert state.down_keys == set()
    assert (LETTER, 0) in events and (SHIFT, 0) in events


def test_super_tap_releases_when_no_combo_follows(board):
    clock, events, state = board
    state.key_down(SUPER_CODE)
    clock.t = 0.05
    state.key_up(SUPER_CODE)
    assert state.mod_state(SUPER_CODE) == MOD_ONCE
    clock.t = 0.40
    state.tick()
    assert (SUPER_CODE, 0) not in events
    clock.t = 0.56
    state.tick()
    assert events[-1] == (SUPER_CODE, 0)
    assert state.mod_state(SUPER_CODE) == MOD_OFF


def test_super_tap_then_letter_is_a_combo(board):
    clock, events, state = board
    state.key_down(SUPER_CODE)
    clock.t = 0.05
    state.key_up(SUPER_CODE)
    clock.t = 0.20
    state.key_down(LETTER)
    clock.t = 0.25
    state.key_up(LETTER)
    assert events == [(SUPER_CODE, 1), (LETTER, 1), (LETTER, 0), (SUPER_CODE, 0)]
    clock.t = 2.0
    state.tick()
    assert events == [(SUPER_CODE, 1), (LETTER, 1), (LETTER, 0), (SUPER_CODE, 0)]


def test_super_hold_is_momentary(board):
    clock, events, state = board
    state.key_down(SUPER_CODE)
    clock.t = 0.30
    state.key_up(SUPER_CODE)
    assert events == [(SUPER_CODE, 1), (SUPER_CODE, 0)]
    assert state.mod_state(SUPER_CODE) == MOD_OFF


def test_super_double_tap_locks(board):
    clock, events, state = board
    state.key_down(SUPER_CODE)
    clock.t = 0.05
    state.key_up(SUPER_CODE)
    clock.t = 0.10
    state.key_down(SUPER_CODE)
    clock.t = 0.15
    state.key_up(SUPER_CODE)
    assert state.mod_state(SUPER_CODE) == MOD_LOCKED
    clock.t = 2.0
    state.tick()
    assert state.mod_state(SUPER_CODE) == MOD_LOCKED

    clock.t = 2.1
    state.key_down(SUPER_CODE)
    assert state.mod_state(SUPER_CODE) == MOD_OFF
    assert events[-1] == (SUPER_CODE, 0)


def make_mode_state(mode):
    clock = Clock()
    events = []
    state = KeyboardState(
        MODS, lambda code, value: events.append((code, value)), now=clock, mode=mode
    )
    return clock, events, state


def test_hold_mode_modifier_is_only_momentary():
    clock, events, state = make_mode_state("hold")
    state.key_down(SHIFT)
    clock.t = 0.05
    state.key_up(SHIFT)
    assert events == [(SHIFT, 1), (SHIFT, 0)]
    assert state.mod_state(SHIFT) == MOD_OFF

    state.key_down(SHIFT)
    clock.t = 0.30
    state.key_up(SHIFT)
    assert events[-1] == (SHIFT, 0)


def test_sticky_mode_tap_toggles_until_next_key():
    clock, events, state = make_mode_state("sticky")
    state.key_down(SHIFT)
    clock.t = 0.05
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_ONCE
    assert events == [(SHIFT, 1)]

    clock.t = 0.10
    state.key_down(LETTER)
    state.key_up(LETTER)
    assert events == [(SHIFT, 1), (LETTER, 1), (LETTER, 0), (SHIFT, 0)]

    state.key_down(SHIFT)
    clock.t = 0.15
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_ONCE
    state.key_down(SHIFT)
    assert state.mod_state(SHIFT) == MOD_OFF
    assert events[-1] == (SHIFT, 0)


def test_switching_mode_releases_active_modifiers():
    clock, events, state = make_mode_state("hybrid")
    state.key_down(SHIFT)
    clock.t = 0.05
    state.key_up(SHIFT)
    assert state.mod_state(SHIFT) == MOD_ONCE
    state.set_mode("hold")
    assert state.mode == "hold"
    assert state.mod_state(SHIFT) == MOD_OFF
    assert events[-1] == (SHIFT, 0)
