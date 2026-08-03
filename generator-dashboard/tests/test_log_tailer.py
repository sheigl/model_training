"""Tests for the incremental log tailer."""

from log_tailer import LogTailer


def test_tail_returns_last_n_lines(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("\n".join(f"l{i}" for i in range(50)) + "\n")
    assert LogTailer(p).tail(10) == [f"l{i}" for i in range(40, 50)]
    assert LogTailer(p).tail(200) == [f"l{i}" for i in range(50)]


def test_tail_missing_file(tmp_path):
    assert LogTailer(tmp_path / "nope.log").tail() == []


def test_new_lines_incremental(tmp_path):
    p = tmp_path / "inc.log"
    p.write_text("line1\nline2\nline3\n")
    t = LogTailer(p)
    assert t.new_lines() == ["line1", "line2", "line3"]
    assert t.new_lines() == []

    with open(p, "a") as f:
        f.write("line4\n")
    assert t.new_lines() == ["line4"]


def test_partial_line_held_back(tmp_path):
    p = tmp_path / "partial.log"
    p.write_text("one\n")
    t = LogTailer(p)
    t.new_lines()  # consume

    with open(p, "a") as f:
        f.write("two")
    assert t.new_lines() == []

    with open(p, "a") as f:
        f.write(" complete\nthree\n")
    assert t.new_lines() == ["two complete", "three"]


def test_new_lines_missing_file_resets(tmp_path):
    t = LogTailer(tmp_path / "missing.log")
    assert t.new_lines() == []


def test_empty_file(tmp_path):
    p = tmp_path / "empty.log"
    p.write_text("")
    t = LogTailer(p)
    assert t.tail() == []
    assert t.new_lines() == []
