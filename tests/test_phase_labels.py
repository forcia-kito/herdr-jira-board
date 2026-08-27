"""Phase labels: a Jira label the board shows, sorts by, and toggles with `l`."""

import pytest

import board


VERIFY = board.PhaseLabel("jb_効果確認中", "効果確認中")
WAITING = board.PhaseLabel("jb_先方確認待ち", "先方確認待ち")


def issue(key, labels=(), status="進行中"):
    return board.Issue(key=key, summary="", status=status, category="indeterminate",
                       issuetype="Task", labels=list(labels))


# ---- config


def test_parses_a_table_entry():
    assert board.PhaseLabel.parse({"label": "jb_x", "display": "X"}) == board.PhaseLabel("jb_x", "X")


def test_a_bare_string_shows_the_label_as_it_is():
    assert board.PhaseLabel.parse("jb_x") == board.PhaseLabel("jb_x", "jb_x")


def test_an_entry_without_a_label_is_dropped():
    assert board.PhaseLabel.parse({"display": "X"}) is None
    assert board.PhaseLabel.parse("") is None
    assert board.PhaseLabel.parse(42) is None


def test_config_loads_phase_labels(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('site = "https://example.atlassian.net"\nemail = "you@example.com"\n'
                 'api_token = "t"\n'
                 '[[phase_labels]]\nlabel = "jb_効果確認中"\ndisplay = "効果確認中"\n'
                 '[[phase_labels]]\nlabel = "jb_先方確認待ち"\ndisplay = "先方確認待ち"\n')
    assert board.Config.load(p).phase_labels == [VERIFY, WAITING]


def test_phase_labels_default_to_empty(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('site = "https://example.atlassian.net"\nemail = "you@example.com"\n'
                 'api_token = "t"\n')
    assert board.Config.load(p).phase_labels == []


# ---- sorting and lookup


def test_labelled_issues_come_first_in_the_configured_order():
    issues = [issue("X-1"), issue("X-2", ["jb_先方確認待ち"]), issue("X-3", ["jb_効果確認中"])]
    order = [i.key for i in board.sort_by_phase_label(issues, [VERIFY, WAITING])]
    assert order == ["X-3", "X-2", "X-1"]


def test_unlabelled_issues_keep_the_jql_order():
    issues = [issue("X-1"), issue("X-2"), issue("X-3")]
    assert board.sort_by_phase_label(issues, [VERIFY]) == issues


def test_other_labels_do_not_move_a_card():
    """Labels the board knows nothing about (JTH_UAT etc.) must not reorder."""
    issues = [issue("X-1", ["JTH_UAT"]), issue("X-2", ["jb_効果確認中"])]
    assert [i.key for i in board.sort_by_phase_label(issues, [VERIFY])] == ["X-2", "X-1"]


def test_an_issue_with_two_phase_labels_takes_the_best_rank():
    issues = [issue("X-1", ["jb_先方確認待ち"]),
              issue("X-2", ["jb_先方確認待ち", "jb_効果確認中"])]
    assert [i.key for i in board.sort_by_phase_label(issues, [VERIFY, WAITING])] == ["X-2", "X-1"]


def test_phase_labels_of_returns_configured_ones_in_order():
    it = issue("X-1", ["JTH_UAT", "jb_先方確認待ち", "jb_効果確認中"])
    assert board.phase_labels_of(it, [VERIFY, WAITING]) == [VERIFY, WAITING]
    assert board.phase_labels_of(issue("X-2"), [VERIFY]) == []


# ---- the Jira call


class FakeResponse:
    def raise_for_status(self):
        pass


def test_set_label_sends_a_single_add_not_the_whole_list(monkeypatch):
    """Other people's labels must survive, so the `update` verb is required."""
    sent = {}

    def fake_put(self, url, json):
        sent.update(url=url, body=json)
        return FakeResponse()

    monkeypatch.setattr(board.httpx.Client, "put", fake_put)
    cfg = board.Config(site="https://example.atlassian.net", email="e", api_token="t", jql="j")
    board.Jira(cfg).set_label("KAN-1", "jb_効果確認中", True)
    assert sent["url"] == "/rest/api/3/issue/KAN-1"
    assert sent["body"] == {"update": {"labels": [{"add": "jb_効果確認中"}]}}


def test_set_label_removes_with_the_remove_verb(monkeypatch):
    sent = {}
    monkeypatch.setattr(board.httpx.Client, "put",
                        lambda self, url, json: (sent.update(body=json), FakeResponse())[1])
    cfg = board.Config(site="https://example.atlassian.net", email="e", api_token="t", jql="j")
    board.Jira(cfg).set_label("KAN-1", "jb_効果確認中", False)
    assert sent["body"] == {"update": {"labels": [{"remove": "jb_効果確認中"}]}}


# ---- the card and the key


ISSUES = [issue("KAN-1", ["jb_効果確認中"]), issue("KAN-2")]


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(board.Config, "load",
                        classmethod(lambda cls, path=None: board.Config(
                            site="https://example.atlassian.net", email="you@example.com",
                            api_token="t", jql="jql", phase_labels=[VERIFY])))
    monkeypatch.setattr(board.Jira, "search", lambda self: [issue(i.key, i.labels)
                                                            for i in ISSUES])
    monkeypatch.setattr(board, "agent_statuses", lambda: {})
    return board.BoardApp()


async def wait_for_cards(app, pilot):
    for _ in range(50):
        if list(app.query(board.Card)):
            return
        await pilot.pause(0.05)
    raise AssertionError("cards never appeared")


async def wait_for(pilot, predicate):
    for _ in range(50):
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition never became true")


@pytest.mark.asyncio
async def test_the_card_shows_the_display_name_only(app):
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        card = next(c for c in app.query(board.Card) if c.issue.key == "KAN-1")
        text = str(card.render())
        assert "効果確認中" in text
        assert "jb_" not in text


@pytest.mark.asyncio
async def test_l_toggles_the_label_off_when_the_card_has_it(app, monkeypatch):
    calls = []
    monkeypatch.setattr(board.Jira, "set_label",
                        lambda self, key, label, present: calls.append((key, label, present)))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("l")
        await wait_for(pilot, lambda: isinstance(app.screen, board.PhaseLabelPicker))
        await pilot.press("enter")
        await wait_for(pilot, lambda: calls)
        # KAN-1 sorts first because it carries the label, and already having it
        # means the key takes it off.
        assert calls == [("KAN-1", "jb_効果確認中", False)]


@pytest.mark.asyncio
async def test_l_adds_the_label_when_the_card_lacks_it(app, monkeypatch):
    calls = []
    monkeypatch.setattr(board.Jira, "set_label",
                        lambda self, key, label, present: calls.append((key, label, present)))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("down")  # move to KAN-2, which has no phase label
        await pilot.press("l")
        await wait_for(pilot, lambda: isinstance(app.screen, board.PhaseLabelPicker))
        await pilot.press("enter")
        await wait_for(pilot, lambda: calls)
        assert calls == [("KAN-2", "jb_効果確認中", True)]


@pytest.mark.asyncio
async def test_cancelling_the_picker_changes_nothing(app, monkeypatch):
    monkeypatch.setattr(board.Jira, "set_label",
                        lambda *a: pytest.fail("must not run when cancelled"))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("l")
        await wait_for(pilot, lambda: isinstance(app.screen, board.PhaseLabelPicker))
        await pilot.press("escape")
        await pilot.pause()


@pytest.mark.asyncio
async def test_l_without_configured_labels_only_notifies(monkeypatch):
    monkeypatch.setattr(board.Config, "load",
                        classmethod(lambda cls, path=None: board.Config(
                            site="https://example.atlassian.net", email="you@example.com",
                            api_token="t", jql="jql")))
    monkeypatch.setattr(board.Jira, "search", lambda self: [issue("KAN-1")])
    monkeypatch.setattr(board, "agent_statuses", lambda: {})
    app = board.BoardApp()
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("l")
        await pilot.pause()
        assert not isinstance(app.screen, board.PhaseLabelPicker)
