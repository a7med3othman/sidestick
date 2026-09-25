import json

from controller_companion import config
from controller_companion.layout import ROWS, KeyboardModel, key_text


def test_rows_are_equal_width():
    widths = {sum(k.width for k in row) for row in ROWS}
    assert widths == {15.0}


def test_vertical_move_lands_on_key_below():
    m = KeyboardModel()
    m.select(1, 1)                      # q
    m.move(0, 1)
    assert m.selected.normal == "a"
    m.move(0, 1)
    assert m.selected.normal == "z"
    m.move(0, 1)
    assert m.selected.action == "delete"      # Z sits above Del
    m.select(3, 5)                            # b
    m.move(0, 1)
    assert m.selected.action == "space"
    m.move(0, -1)
    assert m.selected.normal == "b"           # centre of the space bar


def test_move_clamps_at_edges():
    m = KeyboardModel()
    m.select(0, 0)
    assert not m.move(-1, 0) and not m.move(0, -1)
    m.select(4, 5)
    assert not m.move(1, 0) and not m.move(0, 1)


def test_key_text():
    q = ROWS[1][1]
    one = ROWS[0][1]
    assert key_text(q, False, False) == "q"
    assert key_text(q, True, False) == "Q"
    assert key_text(q, False, True) == "Q"
    assert key_text(q, True, True) == "q"
    assert key_text(one, True, True) == "!"


def test_settings_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = config.Settings(mouse_speed=30, start_minimized=True)
    config.save(s, str(p))
    assert config.load(str(p)) == s


def test_settings_bad_values_fall_back(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"mouse_speed": "fast", "deadzone": 9,
                             "start_minimized": 1, "unknown": 3}))
    s = config.load(str(p))
    assert s.mouse_speed == config.Settings().mouse_speed
    assert s.deadzone == config.LIMITS["deadzone"][1]
    assert s.start_minimized is False


def test_settings_corrupt_file(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    assert config.load(str(p)) == config.Settings()
    assert config.load(str(tmp_path / "missing.json")) == config.Settings()
