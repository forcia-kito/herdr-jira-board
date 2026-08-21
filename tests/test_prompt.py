import board


def text(value):
    return {"type": "text", "text": value}


def para(*content):
    return {"type": "paragraph", "content": list(content)}


DOC = {"type": "doc", "content": [
    para(text("first line"), {"type": "hardBreak"}, text("second line")),
    {"type": "bulletList", "content": [
        {"type": "listItem", "content": [para(text("one"))]},
        {"type": "listItem", "content": [para(text("two"))]},
    ]},
    para({"type": "mention", "attrs": {"text": "@kito"}}, text(" please")),
]}


def test_adf_to_text_renders_blocks_and_bullets():
    assert board.adf_to_text(DOC) == (
        "first line\nsecond line\n"
        "- one\n"
        "- two\n"
        "@kito please\n"
    )


def test_adf_to_text_tolerates_junk():
    assert board.adf_to_text(None) == ""
    assert board.adf_to_text("plain") == ""
    assert board.adf_to_text({"type": "unknown"}) == ""


def test_clip_description_keeps_short_text():
    assert board.clip_description("short") == "short"


def test_clip_description_truncates_long_text():
    long = "x" * (board.DESCRIPTION_LIMIT + 100)
    clipped = board.clip_description(long)
    assert clipped.startswith("x" * board.DESCRIPTION_LIMIT)
    assert len(clipped) < len(long)
    assert not clipped.endswith("x")  # the truncation marker is appended


CFG = board.Config(site="https://example.atlassian.net", email="you@example.com",
                   api_token="t", jql="jql")
ISSUE = board.Issue(key="KAN-1", summary="first", status="進行中", category="indeterminate",
                    issuetype="Task", duedate="2026-08-31")


def test_initial_prompt_includes_issue_fields(monkeypatch):
    monkeypatch.setattr(board, "handoff_note", lambda key: "")
    prompt = board.initial_prompt(ISSUE, CFG)
    assert "KAN-1" in prompt
    assert "進行中" in prompt
    assert "2026-08-31" in prompt
    assert "https://example.atlassian.net/browse/KAN-1" in prompt


def test_initial_prompt_puts_description_before_the_instruction(monkeypatch):
    monkeypatch.setattr(board, "handoff_note", lambda key: "")
    prompt = board.initial_prompt(ISSUE, CFG, "the description body")
    instruction = board.t("prompt_instruction")
    assert "the description body" in prompt
    assert prompt.index("the description body") < prompt.index(instruction)


def test_initial_prompt_without_description_has_no_description_block(monkeypatch):
    monkeypatch.setattr(board, "handoff_note", lambda key: "")
    label = board.t("prompt_description", description="X").split("X")[0]
    assert label not in board.initial_prompt(ISSUE, CFG)
