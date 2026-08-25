import json
import subprocess

import board


def test_sessions_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(board, "SESSIONS_PATH", tmp_path / "state" / "sessions.json")
    board.save_sessions({"KAN-1": "w1:p2"})
    assert board.load_sessions() == {"KAN-1": "w1:p2"}


def test_sessions_corrupt_falls_back(tmp_path, monkeypatch):
    p = tmp_path / "sessions.json"
    p.write_text("{not json")
    monkeypatch.setattr(board, "SESSIONS_PATH", p)
    assert board.load_sessions() == {}


def test_sessions_missing_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "SESSIONS_PATH", tmp_path / "nope.json")
    assert board.load_sessions() == {}


def test_claude_sessions_roundtrip():
    assert board.load_claude_sessions() == {}
    board.save_claude_sessions({"KAN-1": "sess-1"})
    assert board.load_claude_sessions() == {"KAN-1": "sess-1"}


def test_find_key_nested():
    data = {"result": {"tabs": [{"pane": {"pane_id": "w1:p9"}}]}}
    assert board.find_key(data, "pane_id") == "w1:p9"
    assert board.find_key(data, "absent") is None


def fake_run(payload):
    def run(cmd, capture_output=True, text=True, check=True):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
    return run


def test_agent_statuses(monkeypatch):
    payload = {"result": {"agents": [
        {"pane_id": "w1:p1", "agent_status": "working"},
        {"pane_id": "w1:p2", "status": "idle"},
        {"name": "no-pane"},
    ]}}
    monkeypatch.setattr(board.subprocess, "run", fake_run(payload))
    assert board.agent_statuses() == {"w1:p1": "working", "w1:p2": "idle"}


def test_find_session_pane(monkeypatch):
    payload = {"result": {"agents": [
        {"name": "kan-2-p5", "pane_id": "w1:p5"},
        {"name": "other", "pane_id": "w1:p6"},
    ]}}
    monkeypatch.setattr(board.subprocess, "run", fake_run(payload))
    assert board.find_session_pane("KAN-2") == "w1:p5"
    assert board.find_session_pane("KAN-9") is None
