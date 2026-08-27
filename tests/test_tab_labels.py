import board


def herdr_stub(monkeypatch, panes, tabs):
    """Replace board.herdr with a stub serving pane/tab lists; returns the call log."""
    monkeypatch.delenv("HERDR_TAB_ID", raising=False)
    calls = []

    def fake(*args):
        calls.append(args)
        if args[:2] == ("pane", "list"):
            return {"panes": panes}
        if args[:2] == ("tab", "list"):
            return {"tabs": tabs}
        return {}

    monkeypatch.setattr(board, "herdr", fake)
    return calls


def renames(calls):
    return [c for c in calls if c[:2] == ("tab", "rename")]


def test_tab_label_carries_the_status_icon():
    assert board.tab_label_for("KAN-1", "working") == "● KAN-1"
    assert board.tab_label_for("KAN-1", "blocked") == "■ KAN-1"
    assert board.tab_label_for("KAN-1", "done") == "✔ KAN-1"
    assert board.tab_label_for("KAN-1", "idle") == "○ KAN-1"


def test_tab_label_falls_back_to_the_bare_base():
    assert board.tab_label_for("KAN-1", None) == "KAN-1"
    assert board.tab_label_for("KAN-1", "somethingelse") == "KAN-1"


def test_strip_takes_off_only_a_leading_icon():
    assert board.strip_status_icon("● KAN-1") == "KAN-1"
    assert board.strip_status_icon("✔ my tab") == "my tab"
    assert board.strip_status_icon("KAN-1") == "KAN-1"
    assert board.strip_status_icon("my ● tab") == "my ● tab"


def test_sync_renames_to_match_the_status(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": "KAN-1"}],
    )
    board.sync_tab_labels({"w1:p2": "working"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == [("tab", "rename", "w1:t2", "● KAN-1")]


def test_sync_keeps_a_user_renamed_label_and_adds_the_icon(monkeypatch):
    """Only the leading icon is the board's; the user's name stays."""
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": "my tab"}],
    )
    board.sync_tab_labels({"w1:p2": "working"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == [("tab", "rename", "w1:t2", "● my tab")]


def test_sync_swaps_the_icon_when_the_status_changes(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": "● my tab"}],
    )
    board.sync_tab_labels({"w1:p2": "done"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == [("tab", "rename", "w1:t2", "✔ my tab")]


def test_sync_takes_the_icon_off_when_the_agent_is_gone(monkeypatch):
    """{} is a real answer (no agents), so the icon comes off like the badge."""
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": "● my tab"}],
    )
    board.sync_tab_labels({}, {"KAN-1": "w1:p2"})
    assert renames(calls) == [("tab", "rename", "w1:t2", "my tab")]


def test_sync_skips_a_label_that_is_already_right(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": "● KAN-1"}],
    )
    board.sync_tab_labels({"w1:p2": "working"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == []


def test_sync_does_nothing_when_statuses_are_unknown(monkeypatch):
    """None (herdr unreachable) must leave the labels as they are."""
    calls = herdr_stub(monkeypatch, panes=[], tabs=[])
    board.sync_tab_labels(None, {"KAN-1": "w1:p2"})
    assert calls == []


def test_sync_skips_sessions_whose_tab_is_gone(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[],
        tabs=[{"tab_id": "w1:t2", "label": "KAN-1"}],
    )
    board.sync_tab_labels({"w1:p2": "working"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == []


def test_sync_falls_back_to_the_key_when_the_label_is_empty(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p2", "tab_id": "w1:t2"}],
        tabs=[{"tab_id": "w1:t2", "label": ""}],
    )
    board.sync_tab_labels({"w1:p2": "working"}, {"KAN-1": "w1:p2"})
    assert renames(calls) == [("tab", "rename", "w1:t2", "● KAN-1")]


def test_aggregate_prefers_the_attention_worthy_status():
    assert board.aggregate_status(["working", "blocked"]) == "blocked"
    assert board.aggregate_status(["idle", "working"]) == "working"
    assert board.aggregate_status(["idle", "done"]) == "done"
    assert board.aggregate_status([]) is None


def test_sync_covers_every_agent_tab_of_the_workspace(monkeypatch):
    """A tab the board never launched (the user's own Claude, the companion)
    gets the icon too, like the sidebar spaces."""
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p3", "tab_id": "w1:t5"}],
        tabs=[{"tab_id": "w1:t5", "label": "board-custom", "workspace_id": "w1"}],
    )
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t1")
    board.sync_tab_labels({"w1:p3": "working"}, {})
    assert renames(calls) == [("tab", "rename", "w1:t5", "● board-custom")]


def test_sync_clears_the_icon_of_a_tab_whose_agents_are_gone(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p1", "tab_id": "w1:t1"}],
        tabs=[{"tab_id": "w1:t1", "label": "● board-custom", "workspace_id": "w1"}],
    )
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t1")
    board.sync_tab_labels({}, {})
    assert renames(calls) == [("tab", "rename", "w1:t1", "board-custom")]


def test_sync_aggregates_a_tab_with_several_agents(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w1:p1", "tab_id": "w1:t1"},
               {"pane_id": "w1:p2", "tab_id": "w1:t1"}],
        tabs=[{"tab_id": "w1:t1", "label": "pair", "workspace_id": "w1"}],
    )
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t1")
    board.sync_tab_labels({"w1:p1": "working", "w1:p2": "blocked"}, {})
    assert renames(calls) == [("tab", "rename", "w1:t1", "■ pair")]


def test_sync_leaves_other_workspaces_tabs_alone(monkeypatch):
    calls = herdr_stub(
        monkeypatch,
        panes=[{"pane_id": "w2:p1", "tab_id": "w2:t1"}],
        tabs=[{"tab_id": "w2:t1", "label": "elsewhere", "workspace_id": "w2"}],
    )
    monkeypatch.setenv("HERDR_TAB_ID", "w1:t1")
    board.sync_tab_labels({"w2:p1": "working"}, {})
    assert renames(calls) == []
