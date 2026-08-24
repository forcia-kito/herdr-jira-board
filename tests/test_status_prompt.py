import subprocess

import pytest

import board


CFG = board.Config(site="https://example.atlassian.net", email="you@example.com",
                   api_token="t", jql="jql")
ISSUE = board.Issue(key="KAN-1", summary="first", status="進行中", category="indeterminate",
                    issuetype="Task", duedate="2026-08-31")


def test_status_prompt_asks_for_the_three_lines():
    prompt = board.status_prompt()
    for line in board.t("status_lines").splitlines():
        assert line in prompt


def test_initial_prompt_asks_for_the_same_three_lines(monkeypatch):
    """Both entry points open with the same shape, launched or already running."""
    monkeypatch.setattr(board, "handoff_note", lambda key: "")
    prompt = board.initial_prompt(ISSUE, CFG)
    for line in board.t("status_lines").splitlines():
        assert line in prompt


class FakeHerdr:
    """Answer herdr calls, optionally failing the ones a caller wants to fail."""

    def __init__(self, failing=()):
        self.calls = []
        self.failing = failing

    def __call__(self, *args):
        self.calls.append(list(args))
        if args[:2] in self.failing:
            raise subprocess.CalledProcessError(1, ["herdr", *args], output="", stderr="nope")
        return {}

    def commands(self):
        return [c[:2] for c in self.calls]


def test_send_prompt_sends_the_text(monkeypatch):
    fake = FakeHerdr()
    monkeypatch.setattr(board, "herdr", fake)
    board.send_prompt("w1:p5", "hello")
    assert fake.calls[0][:4] == ["agent", "prompt", "w1:p5", "hello"]


def test_send_prompt_presses_enter_when_the_submit_is_swallowed(monkeypatch):
    """The text lands but the agent never starts: press Enter, don't resend."""
    fake = FakeHerdr(failing=(("agent", "prompt"), ("agent", "wait")))
    monkeypatch.setattr(board, "herdr", fake)
    with pytest.raises(subprocess.CalledProcessError):
        board.send_prompt("w1:p5", "hello")
    assert ["agent", "send-keys"] in fake.commands()
    assert len([c for c in fake.calls if c[:2] == ["agent", "prompt"]]) == 1


def test_ready_statuses_exclude_the_ones_that_await_the_user():
    """Sending text to a blocked/waiting agent would answer its dialog."""
    assert "idle" in board.READY_STATUSES
    for busy in ("working", "blocked", "waiting"):
        assert busy not in board.READY_STATUSES
