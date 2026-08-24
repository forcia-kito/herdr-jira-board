"""reload_config() picks up config.toml edits on refresh."""

import pytest

import board


BASE = 'site = "https://example.atlassian.net"\nemail = "you@example.com"\n'


class Stub:
    """Just enough of BoardApp for reload_config to run off the event loop."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.jira = board.Jira(cfg)
        self.notices: list[tuple[str, str]] = []

    def notify(self, message, severity="information"):
        self.notices.append((message, severity))

    def call_from_thread(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    reload_config = board.BoardApp.reload_config


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(board, "CONFIG_PATH", path)
    original_load = board.Config.load
    monkeypatch.setattr(board.Config, "load",
                        classmethod(lambda cls, p=None: original_load.__func__(cls, p or path)))
    return path


@pytest.fixture
def stub(config_path):
    config_path.write_text(BASE + 'api_token = "tok"\n')
    app = Stub(board.Config.load())
    yield app
    app.jira.http.close()


def test_picks_up_edited_settings(stub, config_path):
    config_path.write_text(
        BASE + 'api_token = "tok"\njql = "project = X"\n'
        'exclude_statuses = ["Resolved"]\nstatus_order = ["進行中"]\n'
        '[project_dirs]\nX = "~/x"\n')
    stub.reload_config()
    assert stub.cfg.jql == "project = X"
    assert stub.cfg.status_order == ["進行中"]
    assert stub.cfg.project_dirs == {"X": "~/x"}
    assert stub.notices == []


def test_search_sees_the_new_settings(stub, config_path):
    """Jira reads jql/exclude_statuses off its own cfg, so that must update too."""
    before = stub.jira
    config_path.write_text(BASE + 'api_token = "tok"\njql = "project = X"\n')
    stub.reload_config()
    assert stub.jira is before  # credentials unchanged, client reused
    assert stub.jira.cfg.jql == "project = X"


def test_changed_credentials_rebuild_the_client(stub, config_path):
    before = stub.jira
    config_path.write_text(BASE + 'api_token = "rotated"\n')
    stub.reload_config()
    assert stub.jira is not before
    assert before.http.is_closed
    assert stub.jira.cfg.api_token == "rotated"


def test_broken_file_keeps_the_previous_settings(stub, config_path):
    config_path.write_text("this is not = valid = toml\n")
    stub.reload_config()
    assert stub.cfg.jql  # untouched
    assert stub.cfg.api_token == "tok"
    assert [severity for _, severity in stub.notices] == ["error"]


def test_missing_file_keeps_the_previous_settings(stub, config_path):
    """Config.load raises SystemExit for a missing file; the board must survive."""
    config_path.unlink()
    stub.reload_config()
    assert stub.cfg.api_token == "tok"
    assert [severity for _, severity in stub.notices] == ["error"]


def test_language_change_asks_for_a_restart(stub, config_path):
    original = board.LANG
    try:
        board.LANG = "en"  # pin it: the ambient locale may already be "ja"
        config_path.write_text(BASE + 'api_token = "tok"\nlanguage = "ja"\n')
        stub.reload_config()
        assert [severity for _, severity in stub.notices] == ["warning"]
    finally:
        board.LANG = original


def test_unchanged_language_stays_quiet(stub, config_path):
    original = board.LANG
    try:
        board.LANG = "en"
        config_path.write_text(BASE + 'api_token = "tok"\nlanguage = "en"\n')
        stub.reload_config()
        assert stub.notices == []
    finally:
        board.LANG = original
