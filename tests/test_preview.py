import json
from pathlib import Path

import board


def entry(text=None, *, type="assistant", sidechain=False, content=None):
    if content is None:
        content = [{"type": "text", "text": text}] if text is not None else []
    line = {"type": type, "message": {"content": content}}
    if sidechain:
        line["isSidechain"] = True
    return json.dumps(line)


def transcript(tmp_path, lines) -> Path:
    path = tmp_path / "sess.jsonl"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_last_assistant_text_returns_the_latest_reply(tmp_path):
    path = transcript(tmp_path, [
        entry("first answer"),
        entry("a question", type="user"),
        entry("latest answer"),
    ])
    assert board.last_assistant_text(path) == "latest answer"


def test_last_assistant_text_skips_tool_only_and_sidechain_entries(tmp_path):
    path = transcript(tmp_path, [
        entry("the real reply"),
        entry(content=[{"type": "tool_use", "name": "Bash", "input": {}}]),
        entry("a subagent reply", sidechain=True),
    ])
    assert board.last_assistant_text(path) == "the real reply"


def test_last_assistant_text_joins_the_text_parts(tmp_path):
    path = transcript(tmp_path, [
        entry(content=[{"type": "text", "text": "part one"},
                       {"type": "tool_use", "name": "Bash", "input": {}},
                       {"type": "text", "text": "part two"}]),
    ])
    assert board.last_assistant_text(path) == "part one\npart two"


def test_last_assistant_text_tolerates_junk(tmp_path):
    path = transcript(tmp_path, [
        entry("good"),
        "not json at all",
        json.dumps({"type": "assistant", "message": "not a dict"}),
        json.dumps(["not", "a", "dict"]),
    ])
    assert board.last_assistant_text(path) == "good"


def test_last_assistant_text_empty_cases(tmp_path):
    assert board.last_assistant_text(tmp_path / "absent.jsonl") == ""
    assert board.last_assistant_text(transcript(tmp_path, [entry(type="user")])) == ""


def test_last_assistant_text_reads_only_the_tail_of_a_big_file(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "TRANSCRIPT_TAIL_BYTES", 200)
    filler = entry("x" * 500)  # pushes itself out of the 200-byte tail
    path = transcript(tmp_path, [filler, entry("tail reply")])
    assert board.last_assistant_text(path) == "tail reply"
