"""The card names the issue's type, so bugs and improvements are told apart."""

import board


def issue(key, issuetype, status="進行中"):
    return board.Issue(key=key, summary="summary", status=status,
                       category="indeterminate", issuetype=issuetype)


def test_the_card_names_the_issue_type():
    assert "バグ" in str(board.Card(issue("KAN-1", "バグ")).render())


def test_the_card_leaves_the_status_to_the_divider():
    """The status divider above the card already says it; saying it twice is noise."""
    assert "進行中" not in str(board.Card(issue("KAN-1", "バグ")).render())


def test_the_card_shows_the_type_of_every_issue():
    """No type is treated as the uninteresting default and left off the card."""
    for issuetype in ("バグ", "改善", "新機能", "仕様変更", "タスク"):
        assert issuetype in str(board.Card(issue("KAN-1", issuetype)).render())


# ---- the colour


def config(**kw):
    return board.Config(site="https://example.atlassian.net", email="e",
                        api_token="t", jql="j", **kw)


def test_config_reads_the_issue_type_colours(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('site = "https://example.atlassian.net"\nemail = "you@example.com"\n'
                 'api_token = "t"\n'
                 '[issuetype_colors]\n"バグ" = "red"\n"改善" = "cyan"\n')
    assert board.Config.load(p).issuetype_colors == {"バグ": "red", "改善": "cyan"}


def test_issue_type_colours_default_to_empty(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('site = "https://example.atlassian.net"\nemail = "you@example.com"\n'
                 'api_token = "t"\n')
    assert board.Config.load(p).issuetype_colors == {}


def test_a_blank_colour_is_dropped(tmp_path):
    """An entry left empty must not produce the markup tag `[]`."""
    p = tmp_path / "config.toml"
    p.write_text('site = "https://example.atlassian.net"\nemail = "you@example.com"\n'
                 'api_token = "t"\n[issuetype_colors]\n"バグ" = ""\n')
    assert board.Config.load(p).issuetype_colors == {}


def test_a_configured_type_is_drawn_in_its_colour():
    assert board.kind_markup(issue("KAN-1", "バグ"), "red") == "[red]バグ[/]"


def test_an_unconfigured_type_stays_dim():
    assert board.kind_markup(issue("KAN-1", "タスク"), "") == "[dim]タスク[/]"


def test_the_card_uses_the_colour_it_is_given():
    """The colour reaches the card, not just the helper."""
    text = str(board.Card(issue("KAN-1", "バグ"), issuetype_color="red").render())
    assert "バグ" in text
