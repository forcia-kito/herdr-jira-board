import board


def popen_spy(monkeypatch, openers=("wslview",)):
    """Record Popen calls and pretend only `openers` are installed."""
    calls = []
    monkeypatch.setattr(board.shutil, "which",
                        lambda name: f"/usr/bin/{name}" if name in openers else None)
    monkeypatch.setattr(board.subprocess, "Popen",
                        lambda argv, **kwargs: calls.append((argv, kwargs)))
    return calls


def test_open_url_runs_the_first_installed_opener(monkeypatch):
    calls = popen_spy(monkeypatch)
    board.open_url("https://example.atlassian.net/browse/KAN-1")
    (argv, kwargs), = calls
    assert argv == ["/usr/bin/wslview", "https://example.atlassian.net/browse/KAN-1"]


def test_open_url_does_not_inherit_the_boards_directory(monkeypatch):
    """The board's cwd can be a removed worktree; a Windows binary cannot be
    launched from a deleted directory on WSL, so the opener is anchored."""
    calls = popen_spy(monkeypatch)
    board.open_url("https://example.atlassian.net/browse/KAN-1")
    (_, kwargs), = calls
    assert kwargs["cwd"] == "/"


def test_open_url_falls_back_to_webbrowser_without_an_opener(monkeypatch):
    calls = popen_spy(monkeypatch, openers=())
    opened = []
    monkeypatch.setattr(board.webbrowser, "open", lambda url: opened.append(url))
    board.open_url("https://example.atlassian.net/browse/KAN-1")
    assert calls == []
    assert opened == ["https://example.atlassian.net/browse/KAN-1"]
