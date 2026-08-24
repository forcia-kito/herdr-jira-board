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


async def stage(app, pilot, key, presses=1):
    """Focus the card and stage a move that many columns to the right."""
    card = next(c for c in app.query(board.Card) if c.issue.key == key)
    card.focus()
    await pilot.pause()
    for _ in range(presses):
        await pilot.press("right")
    await pilot.pause()
    return card


async def wait_for(pilot, predicate):
    for _ in range(50):
        if predicate():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition never became true")


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
        await wait_for(pilot, lambda: executed)
        assert executed == [("KAN-1", "41")]


@pytest.mark.asyncio
async def test_staged_moves_accumulate(app):
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        first = await stage(app, pilot, "KAN-1")
        second = await stage(app, pilot, "KAN-2", presses=2)
        assert (first.pending_target, second.pending_target) == ("indeterminate", "done")
        assert column_of(first).category == "indeterminate"
        assert column_of(second).category == "done"


@pytest.mark.asyncio
async def test_confirm_runs_every_staged_move(app, monkeypatch):
    transitions = [
        {"id": "21", "name": "In Progress",
         "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}},
        {"id": "41", "name": "Done", "to": {"name": "Done", "statusCategory": {"key": "done"}}},
    ]
    executed = []
    monkeypatch.setattr(board.Jira, "transitions", lambda self, key: transitions)
    monkeypatch.setattr(board.Jira, "do_transition",
                        lambda self, key, tid: executed.append((key, tid)))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await stage(app, pilot, "KAN-1")
        await stage(app, pilot, "KAN-2", presses=2)
        await pilot.press("enter")
        await wait_for(pilot, lambda: len(executed) == 2)
        assert sorted(executed) == [("KAN-1", "21"), ("KAN-2", "41")]


@pytest.mark.asyncio
async def test_escape_cancels_every_staged_move(app):
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        first = await stage(app, pilot, "KAN-1")
        second = await stage(app, pilot, "KAN-2", presses=2)
        assert (first.pending_target, second.pending_target) == ("indeterminate", "done")
        await pilot.press("escape")
        await pilot.pause()
        assert (first.pending_target, second.pending_target) == (None, None)
        assert all(column_of(c).category == "new" for c in (first, second))


@pytest.mark.asyncio
async def test_picker_runs_once_per_staged_card(app, monkeypatch):
    transitions = [
        {"id": "21", "name": "Start",
         "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}},
        {"id": "31", "name": "Review",
         "to": {"name": "In Review", "statusCategory": {"key": "indeterminate"}}},
    ]
    executed = []
    monkeypatch.setattr(board.Jira, "transitions", lambda self, key: transitions)
    monkeypatch.setattr(board.Jira, "do_transition",
                        lambda self, key, tid: executed.append((key, tid)))
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        await stage(app, pilot, "KAN-1")
        await stage(app, pilot, "KAN-2")
        await pilot.press("enter")
        for _ in range(2):
            await wait_for(pilot, lambda: isinstance(app.screen, board.TransitionPicker))
            await pilot.press("enter")  # take the first candidate
            await pilot.pause()
        await wait_for(pilot, lambda: len(executed) == 2)
        assert sorted(executed) == [("KAN-1", "21"), ("KAN-2", "21")]


@pytest.mark.asyncio
async def test_failed_card_does_not_stop_the_others(app, monkeypatch):
    transitions = [{"id": "21", "name": "In Progress",
                    "to": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}}}]
    executed = []

    def do_transition(self, key, tid):
        if key == "KAN-1":
            raise RuntimeError("boom")
        executed.append((key, tid))

    monkeypatch.setattr(board.Jira, "transitions", lambda self, key: transitions)
    monkeypatch.setattr(board.Jira, "do_transition", do_transition)
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        failing = await stage(app, pilot, "KAN-1")
        other = await stage(app, pilot, "KAN-2")
        assert (failing.pending_target, other.pending_target) == ("indeterminate",) * 2
        await pilot.press("enter")
        await wait_for(pilot, lambda: executed)
        assert executed == [("KAN-2", "21")]
        # The failing card gives up its staged move; the other one still went through.
        assert failing.pending_target is None


def running_session(app, monkeypatch, status):
    """Give KAN-1 a live session in the given agent status, and record the sends."""
    sent = []
    app.sessions = {"KAN-1": "w1:p5"}
    monkeypatch.setattr(board, "agent_statuses", lambda: {"w1:p5": status})
    monkeypatch.setattr(board, "find_session_pane", lambda key: None)
    monkeypatch.setattr(board, "herdr",
                        lambda *args: {"result": {"pane": {"tab_id": "w1:t9"}}})
    monkeypatch.setattr(board, "send_prompt", lambda pane, prompt: sent.append((pane, prompt)))
    return sent


@pytest.mark.asyncio
async def test_enter_on_an_idle_session_asks_where_it_stands(app, monkeypatch):
    sent = running_session(app, monkeypatch, "idle")
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        card = next(c for c in app.query(board.Card) if c.issue.key == "KAN-1")
        card.focus()
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(pilot, lambda: sent)
        assert sent == [("w1:p5", board.status_prompt())]


@pytest.mark.asyncio
async def test_enter_on_a_working_session_does_not_interrupt_it(app, monkeypatch):
    sent = running_session(app, monkeypatch, "working")
    async with app.run_test() as pilot:
        await wait_for_cards(app, pilot)
        card = next(c for c in app.query(board.Card) if c.issue.key == "KAN-1")
        card.focus()
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(10):
            await pilot.pause(0.05)
        assert sent == []
