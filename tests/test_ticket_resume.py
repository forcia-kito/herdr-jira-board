import json
import subprocess

import board


ISSUE = board.Issue(key="KAN-3", summary="third", status="To Do",
                    category="new", issuetype="Task")
CFG = board.Config(site="https://example.atlassian.net", email="you@example.com",
                   api_token="t", jql="jql")


class FakeHerdr:
    """Record every herdr call and answer with a plausible payload."""

    def __init__(self, resume_fails=False):
        self.calls = []
        self.resume_fails = resume_fails

    def __call__(self, cmd, capture_output=True, text=True, check=True):
        args = list(cmd[1:])
        self.calls.append(args)
        if args[:2] == ["tab", "create"]:
            payload = {"result": {"tab": {"tab_id": "w1:t7", "active_pane_id": "w1:p7"}}}
        elif args[:2] == ["agent", "start"]:
            if self.resume_fails and "--resume" in args:
                raise subprocess.CalledProcessError(1, cmd, output="", stderr="no such session")
            payload = {"result": {"agent": {"pane_id": "w1:p7",
                                            "agent_session": {"value": "sess-new"}}}}
        else:
            payload = {"result": {}}
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    def agent_starts(self):
        return [c for c in self.calls if c[:2] == ["agent", "start"]]

    def prompts(self):
        return [c[3] for c in self.calls if c[:2] == ["agent", "prompt"]]


def test_launch_claude_starts_fresh_and_returns_the_session(monkeypatch):
    fake = FakeHerdr()
    monkeypatch.setattr(board.subprocess, "run", fake)
    assert board.launch_claude(ISSUE, CFG, "desc") == ("w1:p7", "sess-new", False)
    assert "--resume" not in fake.agent_starts()[0]
    assert fake.prompts() == [board.initial_prompt(ISSUE, CFG, "desc")]


def test_launch_claude_resumes_the_recorded_session(monkeypatch):
    fake = FakeHerdr()
    monkeypatch.setattr(board.subprocess, "run", fake)
    assert board.launch_claude(ISSUE, CFG, "desc",
                               resume_session="sess-old") == ("w1:p7", "sess-new", True)
    assert fake.agent_starts()[0][-3:] == ["--", "--resume", "sess-old"]
    # The resumed conversation already has its context: ask where it stands
    # instead of restating the issue.
    assert fake.prompts() == [board.status_prompt()]


def test_launch_claude_starts_fresh_when_the_resume_fails(monkeypatch):
    fake = FakeHerdr(resume_fails=True)
    monkeypatch.setattr(board.subprocess, "run", fake)
    assert board.launch_claude(ISSUE, CFG, "desc",
                               resume_session="sess-old") == ("w1:p7", "sess-new", False)
    starts = fake.agent_starts()
    assert "--resume" in starts[0]
    assert "--resume" not in starts[1]
    assert fake.prompts() == [board.initial_prompt(ISSUE, CFG, "desc")]
