from osk.backends.base import DryRunBackend


def test_dry_run_collects_events():
    backend = DryRunBackend("test")
    backend.key(30, 1)
    backend.key(30, 0)
    assert backend.events == [(30, 1), (30, 0)]
    assert backend.name == "dry-run"
