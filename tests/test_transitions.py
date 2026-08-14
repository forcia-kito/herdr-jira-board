import board


def tr(tid, name, to_name, category):
    return {"id": tid, "name": name,
            "to": {"name": to_name, "statusCategory": {"key": category}}}


TRANSITIONS = [
    tr("11", "To Do", "To Do", "new"),
    tr("21", "進行中", "進行中", "indeterminate"),
    tr("31", "レビュー中", "レビュー中", "indeterminate"),
    tr("41", "完了", "完了", "done"),
]


def test_single_candidate():
    got = board.transitions_to_category(TRANSITIONS, "done")
    assert [t["id"] for t in got] == ["41"]


def test_multiple_candidates():
    got = board.transitions_to_category(TRANSITIONS, "indeterminate")
    assert [t["id"] for t in got] == ["21", "31"]


def test_no_candidate():
    assert board.transitions_to_category(TRANSITIONS, "bogus") == []
