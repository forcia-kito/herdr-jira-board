# herdr-jira-board

A [herdr](https://herdr.dev) plugin that shows your Jira board as a kanban TUI
inside herdr, and launches a [Claude Code](https://claude.com/claude-code)
session for any card — with live session status badges on the board.

日本語版は [README.ja.md](README.ja.md) を参照してください。

![demo](demo/demo.gif)

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
- Each card shows its created date and due date; overdue is red, due within
  3 days yellow
- `bin/jira-board --dump` prints the same board as text (or JSON) without the
  TUI, and an optional Claude Code skill lets Claude read it — see
  [Reading the board from Claude](#reading-the-board-from-claude)
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
(`api_token_cmd`, `jql`, `exclude_statuses`, `language`, `[project_dirs]`).

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

## Reading the board from Claude

`--dump` prints the board as text instead of opening the TUI, using the same
config, JQL, exclusions and columns:

```
bin/jira-board --dump          # text
bin/jira-board --dump --json   # machine-readable
```

This is what makes the board readable by a Claude Code session — asking Jira
for the whole board over MCP returns every issue description, which quickly
exceeds what fits in a reply.

A Claude Code skill that wraps it ships in `skills/jira-board`. It is **not**
installed by default; opt in by setting an environment variable, which copies
the skill into `~/.claude/skills` (honouring `CLAUDE_CONFIG_DIR`):

```
HERDR_JIRA_BOARD_INSTALL_SKILL=1 herdr plugin install kiitosu/herdr-jira-board
# already installed? just re-run the build step:
HERDR_JIRA_BOARD_INSTALL_SKILL=1 bin/setup
```

Claude then picks it up when you ask about "the board", and runs the dump for
you. Nothing is written outside `~/.claude/skills/jira-board`, and a directory
already at that path is left alone unless this plugin installed it.

The copy finds the plugin itself, so it keeps working across upgrades. If you
keep your plugins somewhere unusual, point it at the plugin explicitly with
`HERDR_JIRA_BOARD_ROOT`.

## Development

```
git clone https://github.com/kiitosu/herdr-jira-board
herdr plugin link herdr-jira-board   # edits take effect immediately
```

Check the config without opening the TUI: `bin/jira-board --check`  
Print the board without opening the TUI: `bin/jira-board --dump`

Run tests:

```
uv run --with "textual>=0.80" --with "httpx>=0.27" --with pytest --with pytest-asyncio -m pytest tests/
```

## License

[MIT](LICENSE)
