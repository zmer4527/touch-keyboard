from osk.platform.evdev_monitor import INPUT_EVENT, KeyboardMonitor, parse_events, readable_keyboards


def events_for(*items):
    return b"".join(INPUT_EVENT.pack(0, 0, event_type, code, value) for event_type, code, value in items)


def test_parse_events_keeps_partial_frame():
    buffer = bytearray(events_for((1, 30, 1), (1, 31, 0)))
    partial = INPUT_EVENT.pack(0, 0, 1, 32, 1)
    buffer.extend(partial[:7])
    assert parse_events(buffer) == [(1, 30, 1), (1, 31, 0)]
    assert len(buffer) == 7

    buffer.extend(partial[7:])
    assert parse_events(buffer) == [(1, 32, 1)]
    assert len(buffer) == 0


def test_no_devices_gives_empty_list():
    assert readable_keyboards([]) == []


def test_counts_deduplicate_the_same_key_across_devices():
    monitor = KeyboardMonitor()
    seen = []
    monitor.key.connect(lambda code, value: seen.append((code, value)))

    monitor._key("/dev/input/event1", 30, 1)
    monitor._key("/dev/input/event2", 30, 1)
    monitor._key("/dev/input/event1", 30, 0)
    assert seen == [(30, 1)]

    monitor._key("/dev/input/event2", 30, 0)
    assert seen == [(30, 1), (30, 0)]


def test_dropping_a_device_releases_its_keys():
    monitor = KeyboardMonitor()
    seen = []
    monitor.key.connect(lambda code, value: seen.append((code, value)))
    monitor._open[4242] = ("/dev/input/event9", bytearray())
    monitor._down["/dev/input/event9"] = {30}
    monitor._counts[30] = 1

    monitor._drop(4242)
    assert seen == [(30, 0)]
    assert monitor._counts == {}
