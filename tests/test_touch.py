import pytest

from osk.core.state import KeyboardState
from osk.core.touch import TouchRouter

MODS = {42, 54, 29, 97, 56, 100, 125}
SHIFT = 42
LETTER = 30
OTHER = 31


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def router():
    clock = Clock()
    events = []
    state = KeyboardState(MODS, lambda code, value: events.append((code, value)), now=clock)
    return clock, events, TouchRouter(state)


def test_two_fingers_shift_plus_letter(router):
    clock, events, routes = router
    routes.move(1, SHIFT)
    clock.t = 0.05
    routes.release(1)
    assert events == [(SHIFT, 1)]

    clock.t = 0.08
    routes.move(2, LETTER)
    clock.t = 0.10
    routes.release(2)
    assert events == [(SHIFT, 1), (LETTER, 1), (LETTER, 0), (SHIFT, 0)]


def test_held_shift_with_second_finger(router):
    clock, events, routes = router
    routes.move(1, SHIFT)
    clock.t = 0.25
    routes.move(2, LETTER)
    routes.release(2)
    assert events == [(SHIFT, 1), (LETTER, 1), (LETTER, 0)]
    clock.t = 0.30
    routes.release(1)
    assert events[-1] == (SHIFT, 0)


def test_same_key_ignores_second_finger(router):
    _, events, routes = router
    routes.move(1, LETTER)
    routes.move(2, LETTER)
    assert events == [(LETTER, 1)]
    routes.release(2)
    assert events == [(LETTER, 1)]
    routes.release(1)
    assert events == [(LETTER, 1), (LETTER, 0)]


def test_slide_moves_press_between_keys(router):
    _, events, routes = router
    routes.move(1, LETTER)
    routes.move(1, OTHER)
    assert events == [(LETTER, 1), (LETTER, 0), (OTHER, 1)]
    routes.release(1)
    assert events[-1] == (OTHER, 0)
