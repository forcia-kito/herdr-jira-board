import subprocess

import pytest

import board


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
