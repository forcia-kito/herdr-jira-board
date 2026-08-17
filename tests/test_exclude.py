import board


def issue(key, status, category):
    return board.Issue(key=key, summary="", status=status,
                       category=category, issuetype="Task")


ISSUES = [
    issue("X-1", "To Do", "new"),
    issue("X-2", "解決済み", "indeterminate"),
    issue("X-3", "Resolved", "indeterminate"),
    issue("X-4", "完了", "done"),
]


def test_no_exclusions():
    assert board.exclude_by_status(ISSUES, []) == ISSUES


def test_drops_matching_status():
    got = board.exclude_by_status(ISSUES, ["解決済み"])
    assert [i.key for i in got] == ["X-1", "X-3", "X-4"]


def test_match_ignores_case():
    got = board.exclude_by_status(ISSUES, ["resolved"])
    assert [i.key for i in got] == ["X-1", "X-2", "X-4"]


def test_unknown_status_keeps_everything():
    got = board.exclude_by_status(ISSUES, ["Bogus"])
    assert [i.key for i in got] == ["X-1", "X-2", "X-3", "X-4"]


def test_multiple_exclusions():
    got = board.exclude_by_status(ISSUES, ["解決済み", "完了"])
    assert [i.key for i in got] == ["X-1", "X-3"]
