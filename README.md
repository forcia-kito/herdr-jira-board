# herdr-jira-board

A [herdr](https://herdr.dev) plugin that shows your Jira board as a kanban TUI
inside herdr, and launches a [Claude Code](https://claude.com/claude-code)
session for any card — with live session status badges on the board.

日本語版は [README.ja.md](README.ja.md) を参照してください。

## Features

- Issues fetched by JQL, shown in three status-category columns
  (To Do / In Progress / Done) — works across projects with custom workflows.
  By default the board shows your open issues plus issues completed within
  the last 7 days (older Done cards drop off automatically; customizable
  via the `jql` config option)
- Move cards with drag & drop or `←` `→` keys, then confirm with `Enter`
  to run the Jira transition (a picker appears when several transitions apply)
- `Enter` on a card launches a Claude Code session for that issue in a new
  herdr tab, injecting `JIRA_ISSUE_KEY` and an initial prompt with the issue
  summary and URL
- Session status badges (working / blocked / idle / done) on each card,
  refreshed every 5 seconds via `herdr agent list`
- Tab utilities: actions to close other tabs / tabs to the right
- UI in English or Japanese — follows your system locale, can be overridden

## Requirements

- herdr >= 0.7.5 (macOS / Linux)
- Python 3.11+ **or** [uv](https://docs.astral.sh/uv/)
- A Jira Cloud account and an API token

## Install

```
herdr plugin install kiitosu/herdr-jira-board
```

That's it — the install step prepares the Python environment automatically
(uses uv when available, otherwise creates a private virtualenv).

## Configuration

1. Create an API token at
   https://id.atlassian.com/manage-profile/security/api-tokens
   (choose the classic "Create API token", not "with scopes").
2. Copy [config.toml.example](config.toml.example) to the plugin config
   directory and edit it:

```
cp config.toml.example "$(herdr plugin config-dir jira-board)/config.toml"
```

Minimal config:

```toml
site = "https://your-site.atlassian.net"
email = "you@example.com"
api_token = "<your API token>"
```

See the comments in `config.toml.example` for all options
(`api_token_cmd`, `jql`, `language`, `[project_dirs]`).

## Usage

Open the board from inside herdr:

```
herdr plugin pane open --plugin jira-board --entrypoint board
```

Recommended: bind it to a key in `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "prefix+k"
type = "plugin_action"
command = "jira-board.open-board"
description = "Open Jira board"

[[keys.command]]
key = "prefix+x"
type = "plugin_action"
command = "jira-board.close-right-tabs"
description = "Close tabs to the right"

[[keys.command]]
key = "prefix+shift+x"
type = "plugin_action"
command = "jira-board.close-other-tabs"
description = "Close other tabs"
```

### Keys

| Key | Action |
| --- | --- |
| `↑` `↓` | Focus previous / next card |
| `←` `→` | Stage a move to the adjacent column |
| `Enter` | Confirm a staged move, or launch a Claude session for the card |
| `Esc` | Cancel a staged move / unfocus |
| `r` | Refresh the board |
| `o` | Open the issue in the browser |
| `q` | Quit |

Cards can also be dragged between columns with the mouse; drops are staged the
same way and confirmed with `Enter`.

## Development

```
git clone https://github.com/kiitosu/herdr-jira-board
herdr plugin link herdr-jira-board   # edits take effect immediately
```

Check the config without opening the TUI: `bin/jira-board --check`

Run tests:

```
uv run --with "textual>=0.80" --with "httpx>=0.27" --with pytest --with pytest-asyncio -m pytest tests/
```

## License

[MIT](LICENSE)
