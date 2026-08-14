import pytest

import board


ISSUES = [
    board.Issue(key="KAN-1", summary="first", status="To Do", category="new", issuetype="Task"),
    board.Issue(key="KAN-2", summary="second", status="To Do", category="new", issuetype="Task"),
]


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(board.Config, "load",
                        classmethod(lambda cls, path=None: board.Config(
                            site="https://example.atlassian.net", email="you@example.com",
                            api_token="t", jql="jql")))
    monkeypatch.setattr(board.Jira, "search", lambda self: list(ISSUES))
    monkeypatch.setattr(board, "agent_statuses", lambda: {})
    return board.BoardApp()


def column_of(card):
    node = card.parent
    while node is not None and not isinstance(node, board.Column):
        node = node.parent
    return node


async def wait_for_cards(app, pilot):
    for _ in range(50):
        if list(app.query(board.Card)):
            return
        await pilot.pause(0.05)
    raise AssertionError("cards never appeared")


@pytest.mark.asyncio
async def test_initial_focus_and_columns(app):
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        cards = list(app.query(board.Card))
        assert [c.issue.key for c in cards] == ["KAN-1", "KAN-2"]
        assert isinstance(app.focused, board.Card)
        assert app.focused.issue.key == "KAN-1"
        assert all(column_of(c).category == "new" for c in cards)


@pytest.mark.asyncio
async def test_stage_move_and_cancel(app):
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("right")
        await pilot.pause()
        card = next(c for c in app.query(board.Card) if c.issue.key == "KAN-1")
        assert card.pending_target == "indeterminate"
        assert column_of(card).category == "indeterminate"

        await pilot.press("escape")
        await pilot.pause()
        assert card.pending_target is None
        assert column_of(card).category == "new"


@pytest.mark.asyncio
async def test_confirm_runs_single_transition(app, monkeypatch):
    transitions = [{"id": "41", "name": "Done",
                    "to": {"name": "Done", "statusCategory": {"key": "done"}}}]
    executed = []
    monkeypatch.setattr(board.Jira, "transitions", lambda self, key: transitions)
    monkeypatch.setattr(board.Jira, "do_transition",
                        lambda self, key, tid: executed.append((key, tid)))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await pilot.press("right")
        await pilot.press("right")
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(50):
            if executed:
                break
            await pilot.pause(0.05)
        assert executed == [("KAN-1", "41")]
