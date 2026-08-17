import pytest

import board


BASE = 'site = "https://example.atlassian.net/"\nemail = "you@example.com"\n'


def write(tmp_path, text):
    p = tmp_path / "config.toml"
    p.write_text(text)
    return p


def test_load_minimal(tmp_path):
    cfg = board.Config.load(write(tmp_path, BASE + 'api_token = "tok"\n'))
    assert cfg.site == "https://example.atlassian.net"  # trailing slash stripped
    assert cfg.email == "you@example.com"
    assert cfg.api_token == "tok"
    assert "assignee = currentUser()" in cfg.jql  # default JQL
    assert cfg.exclude_statuses == []
    assert cfg.project_dirs == {}


def test_load_full(tmp_path):
    cfg = board.Config.load(write(
        tmp_path,
        BASE + 'api_token = "tok"\njql = "project = X"\n'
        'exclude_statuses = ["Resolved"]\n[project_dirs]\nX = "~/x"\n',
    ))
    assert cfg.jql == "project = X"
    assert cfg.exclude_statuses == ["Resolved"]
    assert cfg.project_dirs == {"X": "~/x"}


def test_api_token_cmd(tmp_path):
    cfg = board.Config.load(write(tmp_path, BASE + 'api_token_cmd = "echo secret"\n'))
    assert cfg.api_token == "secret"


def test_missing_file(tmp_path):
    with pytest.raises(SystemExit) as exc:
        board.Config.load(tmp_path / "missing.toml")
    assert "missing.toml" in str(exc.value)


def test_missing_required_key(tmp_path):
    with pytest.raises(KeyError):
        board.Config.load(write(tmp_path, 'email = "you@example.com"\napi_token = "t"\n'))


def test_language_override(tmp_path):
    original = board.LANG
    try:
        board.Config.load(write(tmp_path, BASE + 'api_token = "t"\nlanguage = "ja"\n'))
        assert board.LANG == "ja"
        assert board.t("quit") == "終了"
        board.Config.load(write(tmp_path, BASE + 'api_token = "t"\nlanguage = "en"\n'))
        assert board.t("quit") == "Quit"
        board.Config.load(write(tmp_path, BASE + 'api_token = "t"\nlanguage = "xx"\n'))
        assert board.LANG == "en"  # invalid value keeps the previous language
    finally:
        board.LANG = original
