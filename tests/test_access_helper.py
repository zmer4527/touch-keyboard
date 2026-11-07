from pathlib import Path


def test_input_access_helper_grants_read_acl():
    script = Path(__file__).resolve().parents[1] / "assets" / "input-access-helper.sh"
    text = script.read_text(encoding="utf-8")
    assert script.is_file()
    assert "setfacl" in text
    assert "/dev/input/event*" in text
    assert 'u:$user:r' in text
