import json
import subprocess

import board


PANES = {"result": {"panes": [
    # the board's own pane
    {"pane_id": "w1:p8", "tab_id": "w1:t5", "label": "Jira Board"},
    # a Claude session next to it
    {"pane_id": "w1:p9", "tab_id": "w1:t5", "agent": "claude", "cwd": "/data/repos/taco",
     "agent_session": {"value": "sess-9"}},
    # a Claude pane whose session id herdr does not know
    {"pane_id": "w1:pA", "tab_id": "w1:t5", "agent": "claude", "cwd": "/data/repos"},
    # a Claude session in another tab
    {"pane_id": "w1:pB", "tab_id": "w1:t9", "agent": "claude", "cwd": "/data/repos/x",
     "agent_session": {"value": "sess-b"}},
]}}


def fake_run(payload):
    def run(cmd, capture_output=True, text=True, check=True):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
    return run


def test_neighbor_sessions_keeps_the_same_tab_only(monkeypatch):
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t5")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p8")
    monkeypatch.setattr(board.subprocess, "run", fake_run(PANES))
    assert board.neighbor_sessions() == [
        {"pane_id": "w1:p9", "session_id": "sess-9", "cwd": "/data/repos/taco"}]


def test_neighbor_sessions_without_tab_env(monkeypatch):
    monkeypatch.delenv("HERDR_TAB_ID", raising=False)
    monkeypatch.setattr(board.subprocess, "run", fake_run(PANES))
    assert board.neighbor_sessions() == []


def test_neighbor_sessions_when_herdr_fails(monkeypatch):
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t5")

    def boom(*a, **kw):
        raise subprocess.CalledProcessError(1, "herdr")

    monkeypatch.setattr(board.subprocess, "run", boom)
    assert board.neighbor_sessions() == []


def test_transcript_path_globs_by_session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    project = tmp_path / "projects" / "-data-repos-taco"
    project.mkdir(parents=True)
    (project / "sess-9.jsonl").write_text("{}")
    assert board.transcript_path("sess-9") == project / "sess-9.jsonl"
    assert board.transcript_path("sess-absent") is None


def test_handoff_note_lists_the_transcripts(monkeypatch, tmp_path):
    monkeypatch.setattr(board, "neighbor_sessions", lambda: [
        {"pane_id": "w1:p9", "session_id": "sess-9", "cwd": "/data/repos/taco"},
        {"pane_id": "w1:pA", "session_id": "sess-a", "cwd": "/data/repos"},
    ])
    monkeypatch.setattr(board, "transcript_path",
                        lambda sid: tmp_path / f"{sid}.jsonl" if sid == "sess-9" else None)
    note = board.handoff_note("KAN-1")
    assert str(tmp_path / "sess-9.jsonl") in note
    assert "/data/repos/taco" in note
    assert "KAN-1" in note
    # a pane without a transcript is left out
    assert "sess-a" not in note


def test_handoff_note_empty_without_neighbors(monkeypatch):
    monkeypatch.setattr(board, "neighbor_sessions", list)
    assert board.handoff_note("KAN-1") == ""


def test_initial_prompt_appends_the_handoff(monkeypatch):
    cfg = board.Config(site="https://example.atlassian.net", email="you@example.com",
                       api_token="t", jql="jql")
    issue = board.Issue(key="KAN-1", summary="first", status="To Do", category="new",
                        issuetype="Task")
    monkeypatch.setattr(board, "handoff_note", lambda key: "")
    plain = board.initial_prompt(issue, cfg)
    assert "KAN-1" in plain
    assert "https://example.atlassian.net/browse/KAN-1" in plain

    monkeypatch.setattr(board, "handoff_note", lambda key: f"HANDOFF {key}")
    assert board.initial_prompt(issue, cfg) == f"{plain}\n\nHANDOFF KAN-1"
