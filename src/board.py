# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=0.80", "httpx>=0.27"]
# ///
"""herdr-jira-board: Jira kanban board TUI.

- Three status-category columns (To Do / In Progress / Done)
- Move cards between columns via drag & drop or arrow keys (runs Jira transitions)
- Enter launches a Claude session for the focused card in a new herdr tab
- Polls `herdr agent list` to show session status badges on cards
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tomllib
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

def resolve_config_path() -> Path:
    """Prefer herdr's per-plugin config dir, fall back to the legacy location."""
    plugin_dir = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if plugin_dir and (p := Path(plugin_dir) / "config.toml").exists():
        return p
    return Path.home() / ".config/herdr-jira-board/config.toml"


CONFIG_PATH = resolve_config_path()
STATE_DIR = Path(os.environ.get("HERDR_PLUGIN_STATE_DIR") or Path.home() / ".local/share/herdr-jira-board")
SESSIONS_PATH = STATE_DIR / "sessions.json"


# ---------------------------------------------------------------- i18n

def detect_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return "ja" if value.lower().startswith("ja") else "en"
    return "en"


LANG = detect_language()

MESSAGES: dict[str, dict[str, str]] = {
    "config_missing": {
        "en": ("Config file not found: {path}\n"
               "Copy config.toml.example from the plugin repository to that path\n"
               "and fill in site / email / api_token (see README.md)."),
        "ja": ("設定ファイルがありません: {path}\n"
               "リポジトリの config.toml.example をこのパスにコピーし、\n"
               "site / email / api_token を設定してください (README.md 参照)。"),
    },
    "move_right": {"en": "Move right", "ja": "右の列へ"},
    "move_left": {"en": "Move left", "ja": "左の列へ"},
    "cancel_or_unfocus": {"en": "Cancel move / unfocus", "ja": "移動取消 / 選択解除"},
    "cancel": {"en": "Cancel", "ja": "キャンセル"},
    "refresh": {"en": "Refresh", "ja": "更新"},
    "confirm_or_launch": {"en": "Confirm / launch Claude", "ja": "確定 / Claude起動"},
    "open_browser": {"en": "Open in browser", "ja": "ブラウザで開く"},
    "next_card": {"en": "Next card", "ja": "次のカード"},
    "prev_card": {"en": "Previous card", "ja": "前のカード"},
    "quit": {"en": "Quit", "ja": "終了"},
    "pending_hint": {"en": "⏎ confirm / Esc cancel", "ja": "⏎確定 / Esc取消"},
    "pick_transition": {"en": "Select a transition for [b]{key}[/b]:",
                        "ja": "[b]{key}[/b] のトランジションを選択:"},
    "fetch_failed": {"en": "Failed to fetch from Jira: {error}", "ja": "Jira 取得失敗: {error}"},
    "transitions_failed": {"en": "Failed to fetch transitions: {error}",
                           "ja": "トランジション取得失敗: {error}"},
    "no_transition": {"en": "{key}: no transition leads to this column",
                      "ja": "{key}: この列へ移動できるトランジションがありません"},
    "transition_failed": {
        "en": "{key}: transition failed (if it requires fields, use the browser): {error}",
        "ja": "{key}: トランジション失敗 (必須フィールドがある場合はブラウザで操作してください): {error}",
    },
    "moved": {"en": "Moved {key}", "ja": "{key} を移動しました"},
    "launching_already": {"en": "A session for {key} is already starting…",
                          "ja": "{key} のセッションを起動中です…"},
    "launching": {"en": "Starting a session for {key}…", "ja": "{key} のセッションを起動しています…"},
    "focus_failed": {"en": "{key}: cannot focus the session: {error}",
                     "ja": "{key}: セッションへ移動できません: {error}"},
    "launch_failed": {"en": "Failed to launch session: {error}", "ja": "セッション起動失敗: {error}"},
    "launched": {"en": "Launched a Claude session for {key}",
                 "ja": "{key} の Claude セッションを起動しました"},
    "no_pane_id": {"en": "Cannot find a pane id in the tab create response: {data}",
                   "ja": "tab create の応答から pane id を特定できません: {data}"},
    "no_tab_id": {"en": "Cannot find tab_id for pane {pane}",
                  "ja": "pane {pane} の tab_id を特定できません"},
    "herdr_failed": {"en": "{command} failed: {detail}", "ja": "{command} が失敗: {detail}"},
    "initial_prompt": {
        "en": ("Let's work on Jira issue {key}.\n"
               "Summary: {summary}\n"
               "URL: {url}\n"
               "Start by understanding the issue and proposing an approach."),
        "ja": ("Jira 課題 {key} の作業をします。\n"
               "サマリ: {summary}\n"
               "URL: {url}\n"
               "まず課題内容を把握し、作業方針を提案してください。"),
    },
}


def t(msg_id: str, **kwargs: object) -> str:
    text = MESSAGES[msg_id].get(LANG) or MESSAGES[msg_id]["en"]
    return text.format(**kwargs) if kwargs else text


def set_language(lang: str | None) -> None:
    """Apply the config override ("en" / "ja"); None keeps auto-detection."""
    global LANG
    if lang in ("en", "ja"):
        LANG = lang


# Key-binding descriptions are fixed at class-definition time, so apply the
# config override before the widget classes below are defined.
try:
    set_language(tomllib.loads(CONFIG_PATH.read_text()).get("language"))
except (OSError, ValueError):
    pass

CATEGORY_COLUMNS = [("new", "To Do"), ("indeterminate", "In Progress"), ("done", "Done")]

STATUS_ICONS = {
    "working": "[yellow]● working[/]",
    "blocked": "[red]■ blocked[/]",
    "waiting": "[red]■ waiting[/]",
    "done": "[green]✔ done[/]",
    "idle": "[dim]○ idle[/]",
}


# ---------------------------------------------------------------- config / state

@dataclass
class Config:
    site: str
    email: str
    api_token: str
    jql: str
    exclude_statuses: list[str] = field(default_factory=list)
    project_dirs: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or CONFIG_PATH
        if not path.exists():
            raise SystemExit(t("config_missing", path=path))
        raw = tomllib.loads(path.read_text())
        set_language(raw.get("language"))
        token = raw.get("api_token", "")
        if not token and raw.get("api_token_cmd"):
            token = subprocess.run(
                ["bash", "-c", raw["api_token_cmd"]], capture_output=True, text=True, check=True
            ).stdout.strip()
        return cls(
            site=raw["site"].rstrip("/"),
            email=raw["email"],
            api_token=token,
            jql=raw.get(
                "jql",
                "assignee = currentUser() AND (statusCategory != Done OR updated >= -7d) ORDER BY updated DESC",
            ),
            exclude_statuses=raw.get("exclude_statuses", []),
            project_dirs=raw.get("project_dirs", {}),
        )


def load_sessions() -> dict[str, str]:
    """issue key -> herdr pane_id"""
    try:
        return json.loads(SESSIONS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def save_sessions(data: dict[str, str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_PATH.write_text(json.dumps(data, indent=1))


# ---------------------------------------------------------------- jira client

@dataclass
class Issue:
    key: str
    summary: str
    status: str
    category: str  # new / indeterminate / done
    issuetype: str


class Jira:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = httpx.Client(
            base_url=cfg.site, auth=(cfg.email, cfg.api_token), timeout=30,
            headers={"Accept": "application/json",
                     # Ask Jira for status/transition names in the UI language
                     # instead of the Jira account's profile language.
                     "Accept-Language": LANG,
                     "X-Force-Accept-Language": "true"},
        )

    def search(self) -> list[Issue]:
        r = self.http.post(
            "/rest/api/3/search/jql",
            json={"jql": self.cfg.jql, "maxResults": 100,
                  "fields": ["summary", "status", "issuetype"]},
        )
        r.raise_for_status()
        issues = []
        for it in r.json().get("issues", []):
            f = it["fields"]
            issues.append(Issue(
                key=it["key"],
                summary=f.get("summary") or "",
                status=f["status"]["name"],
                category=f["status"]["statusCategory"]["key"],
                issuetype=(f.get("issuetype") or {}).get("name", ""),
            ))
        return exclude_by_status(issues, self.cfg.exclude_statuses)

    def transitions(self, key: str) -> list[dict]:
        r = self.http.get(f"/rest/api/3/issue/{key}/transitions")
        r.raise_for_status()
        return r.json().get("transitions", [])

    def do_transition(self, key: str, transition_id: str) -> None:
        r = self.http.post(f"/rest/api/3/issue/{key}/transitions",
                           json={"transition": {"id": transition_id}})
        r.raise_for_status()


def exclude_by_status(issues: list[Issue], excluded: list[str]) -> list[Issue]:
    """Issues whose status name is not listed in `excluded` (case-insensitive).

    Lets a custom workflow status be hidden from the board without rewriting the
    `jql` option, which the user may have customized (including its ORDER BY).
    """
    if not excluded:
        return issues
    drop = {name.casefold() for name in excluded}
    return [i for i in issues if i.status.casefold() not in drop]


def transitions_to_category(transitions: list[dict], target_category: str) -> list[dict]:
    """Transitions whose target status belongs to the given status category."""
    return [tr for tr in transitions
            if tr["to"]["statusCategory"]["key"] == target_category]


# ---------------------------------------------------------------- herdr helpers

def herdr(*args: str) -> dict:
    bin_ = os.environ.get("HERDR_BIN_PATH", "herdr")
    out = subprocess.run([bin_, *args], capture_output=True, text=True, check=True).stdout
    try:
        return json.loads(out)
    except ValueError:
        return {}


def find_key(obj, key: str):
    """Return the first value found for key anywhere in nested JSON."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            if (r := find_key(v, key)) is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            if (r := find_key(v, key)) is not None:
                return r
    return None


def agent_statuses() -> dict[str, str]:
    """herdr pane_id -> agent status"""
    try:
        data = herdr("agent", "list")
    except (subprocess.CalledProcessError, OSError):
        return {}
    agents = find_key(data, "agents") or []
    out = {}
    for a in agents:
        if isinstance(a, dict) and a.get("pane_id"):
            out[str(a["pane_id"])] = str(a.get("agent_status") or a.get("status") or "")
    return out


def find_session_pane(key: str) -> str | None:
    """Find a running agent's pane for the issue key by agent name."""
    try:
        data = herdr("agent", "list")
    except (subprocess.CalledProcessError, OSError):
        return None
    prefix = f"{key.lower()}-"
    for a in find_key(data, "agents") or []:
        if isinstance(a, dict) and str(a.get("name") or "").startswith(prefix) and a.get("pane_id"):
            return str(a["pane_id"])
    return None


def launch_claude(issue: Issue, cfg: Config) -> str:
    """Create a tab for the issue and launch Claude. Returns the pane_id."""
    project = issue.key.split("-")[0]
    cwd = os.path.expanduser(cfg.project_dirs.get(project, "~"))
    tab = herdr(
        "tab", "create", "--cwd", cwd, "--label", issue.key,
        "--env", f"JIRA_ISSUE_KEY={issue.key}", "--no-focus",
    )
    pane_id = find_key(tab, "active_pane_id") or find_key(tab, "pane_id")
    if not pane_id:
        raise RuntimeError(t("no_pane_id", data=tab))
    try:
        agent_name = f"{issue.key.lower()}-{str(pane_id).split(':')[-1].lower()}"
        # Right after tab create the pane's shell may not be up yet and agent
        # start fails with agent_pane_busy ("not an available shell"); retry.
        for attempt in range(20):
            try:
                herdr("agent", "start", agent_name, "--kind", "claude", "--pane", str(pane_id),
                      "--timeout", "60000")
                break
            except subprocess.CalledProcessError as e:
                if attempt < 19 and "agent_pane_busy" in ((e.stdout or "") + (e.stderr or "")):
                    time.sleep(0.5)
                    continue
                raise
        # Claude may not accept input immediately after start; wait until it is
        # idle (prompt ready), then send and confirm the working transition.
        herdr("agent", "wait", str(pane_id), "--until", "idle", "--timeout", "60000")
        prompt = t("initial_prompt", key=issue.key, summary=issue.summary,
                   url=f"{cfg.site}/browse/{issue.key}")
        try:
            herdr("agent", "prompt", str(pane_id), prompt, "--wait", "--until", "working",
                  "--timeout", "30000")
        except subprocess.CalledProcessError:
            # The text usually lands but the submitting Enter can be swallowed.
            # Give the agent a moment, then press Enter instead of resending the
            # text (a resend would duplicate the prompt in the composer).
            try:
                herdr("agent", "wait", str(pane_id), "--until", "working", "--timeout", "10000")
            except subprocess.CalledProcessError:
                herdr("agent", "send-keys", str(pane_id), "enter")
                herdr("agent", "wait", str(pane_id), "--until", "working", "--timeout", "30000")
    except subprocess.CalledProcessError as e:
        # Don't leave the empty tab behind on failure
        tab_id = find_key(tab, "tab_id")
        if tab_id:
            try:
                herdr("tab", "close", str(tab_id))
            except subprocess.CalledProcessError:
                pass
        detail = (e.stderr or e.stdout or "").strip()[:200]
        raise RuntimeError(t("herdr_failed", command=" ".join(e.cmd[1:3]), detail=detail)) from e
    return str(pane_id)


# ---------------------------------------------------------------- widgets

class Card(Static, can_focus=True):
    # VerticalScroll (the column) binds arrow keys to scrolling, so the focused
    # card carries these bindings itself to take precedence.
    BINDINGS = [
        Binding("right", "app.move(1)", t("move_right"), key_display="→"),
        Binding("left", "app.move(-1)", t("move_left"), key_display="←"),
        Binding("escape", "app.cancel_move", t("cancel_or_unfocus"), key_display="Esc"),
    ]

    def __init__(self, issue: Issue):
        super().__init__()
        self.issue = issue
        self.agent_status: str | None = None
        self.pending_target: str | None = None  # target category (unconfirmed)
        self.render_card()

    def render_card(self) -> None:
        badge = ""
        if self.agent_status is not None:
            badge = "  " + STATUS_ICONS.get(self.agent_status, f"[dim]{self.agent_status}[/]")
        pending = f"  [yellow]{t('pending_hint')}[/]" if self.pending_target else ""
        self.update(f"[b]{self.issue.key}[/b] [dim]{self.issue.status}[/]{badge}{pending}\n{self.issue.summary}")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.focus()
        self.capture_mouse()
        self.add_class("dragging")

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self.capture_mouse(False)
        self.remove_class("dragging")
        target = self.screen.get_widget_at(*event.screen_offset)[0]
        while target is not None and not isinstance(target, Column):
            target = target.parent
        if isinstance(target, Column) and target.category != self.issue.category:
            self.app.stage_move(self, target.category)


class Column(VerticalScroll):
    def __init__(self, category: str, title: str):
        super().__init__(classes="column")
        self.category = category
        self.border_title = title


class TransitionPicker(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss(None)", t("cancel"))]

    def __init__(self, issue: Issue, transitions: list[dict]):
        super().__init__()
        self.issue = issue
        self.transitions = transitions

    def compose(self) -> ComposeResult:
        # Append the transition name only when two candidates share the same
        # target status and the label alone would be ambiguous.
        targets = [tr["to"]["name"] for tr in self.transitions]

        def label(tr: dict) -> str:
            base = f"{self.issue.status} → {tr['to']['name']}"
            if targets.count(tr["to"]["name"]) > 1:
                base += f"  [dim]({tr['name']})[/]"
            return base

        with Vertical(id="picker"):
            yield Static(t("pick_transition", key=self.issue.key))
            yield OptionList(*[Option(label(tr), id=tr["id"]) for tr in self.transitions])

    def on_option_list_option_selected(self, ev: OptionList.OptionSelected) -> None:
        self.dismiss(ev.option.id)


# ---------------------------------------------------------------- app

class BoardApp(App):
    TITLE = "Jira Board"
    CSS = """
    Horizontal#columns { height: 1fr; }
    .column { width: 1fr; border: round $primary; margin: 0 1; padding: 0 1; }
    Card { border: round $surface-lighten-2; margin-bottom: 1; padding: 0 1; }
    Card:focus { border: round $accent; }
    Card.dragging { opacity: 0.6; }
    Card.pending { border: round $warning; }
    #picker { width: 60; height: auto; max-height: 20; border: thick $accent; background: $surface; padding: 1; }
    TransitionPicker { align: center middle; }
    """
    BINDINGS = [
        Binding("r", "refresh", t("refresh")),
        Binding("enter", "confirm_or_launch", t("confirm_or_launch")),
        Binding("escape", "cancel_move", t("cancel_or_unfocus"), show=False),
        Binding("o", "open_browser", t("open_browser")),
        Binding("down", "focus_next", t("next_card"), show=False),
        Binding("up", "focus_previous", t("prev_card"), show=False),
        Binding("q", "quit", t("quit")),
    ]

    def __init__(self):
        super().__init__()
        self.cfg = Config.load()
        self.jira = Jira(self.cfg)
        self.sessions = load_sessions()
        self._launching: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="columns"):
            for cat, title in CATEGORY_COLUMNS:
                yield Column(cat, title)
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()
        self.set_interval(5, self.update_badges)

    # ---- data loading

    @work(thread=True, exclusive=True)
    def action_refresh(self) -> None:
        try:
            issues = self.jira.search()
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(self.notify, t("fetch_failed", error=e), severity="error")
            return
        self.call_from_thread(self.populate, issues)

    def populate(self, issues: list[Issue]) -> None:
        for col in self.query(Column):
            col.remove_children()
            for issue in issues:
                if issue.category == col.category:
                    col.mount(Card(issue))
        if (first := next(iter(self.query(Card)), None)) is not None:
            first.focus()
        self.update_badges()

    @work(thread=True, exclusive=True, group="badges")
    def update_badges(self) -> None:
        statuses = agent_statuses()
        self.call_from_thread(self.apply_badges, statuses)

    def apply_badges(self, statuses: dict[str, str]) -> None:
        for card in self.query(Card):
            agent = self.sessions.get(card.issue.key)
            new = statuses.get(agent) if agent else None
            if new != card.agent_status:
                card.agent_status = new
                card.render_card()

    # ---- card movement / transitions

    def focused_card(self) -> Card | None:
        return self.focused if isinstance(self.focused, Card) else None

    def action_move(self, direction: int) -> None:
        card = self.focused_card()
        if not card:
            return
        cats = [c for c, _ in CATEGORY_COLUMNS]
        current = card.pending_target or card.issue.category
        idx = cats.index(current) + direction
        if not 0 <= idx < len(cats):
            return
        if cats[idx] == card.issue.category:
            self.cancel_move(card)
        else:
            self.stage_move(card, cats[idx])

    # ---- pending move (move visually only; Enter confirms, Esc cancels)

    def stage_move(self, card: Card, target_category: str) -> None:
        for other in self.query(Card):
            if other is not card and other.pending_target:
                self.cancel_move(other)
        self.mount_card_in(card, target_category)
        card.pending_target = target_category
        card.add_class("pending")
        card.render_card()

    def cancel_move(self, card: Card | None = None) -> None:
        card = card or self.focused_card()
        if not card or not card.pending_target:
            return
        self.mount_card_in(card, card.issue.category)
        card.pending_target = None
        card.remove_class("pending")
        card.render_card()

    def action_cancel_move(self) -> None:
        card = self.focused_card()
        if card and card.pending_target:
            self.cancel_move(card)
        elif card:
            self.set_focus(None)

    def mount_card_in(self, card: Card, category: str) -> None:
        column = next(c for c in self.query(Column) if c.category == category)

        async def _move() -> None:
            await card.remove()
            await column.mount(card)
            card.focus()

        self.run_worker(_move(), exclusive=False)

    def action_confirm_or_launch(self) -> None:
        card = self.focused_card()
        if not card:
            return
        if card.pending_target:
            self.run_move(card, card.pending_target)
        else:
            self.action_launch()

    @work(thread=True)
    def run_move(self, card: Card, target_category: str) -> None:
        key = card.issue.key
        try:
            candidates = transitions_to_category(self.jira.transitions(key), target_category)
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(self.notify, t("transitions_failed", error=e), severity="error")
            self.call_from_thread(self.cancel_move, card)
            return
        if not candidates:
            self.call_from_thread(
                self.notify, t("no_transition", key=key), severity="warning")
            self.call_from_thread(self.cancel_move, card)
            return
        if len(candidates) == 1:
            self.execute_transition(card, candidates[0]["id"], target_category)
        else:
            self.call_from_thread(self.pick_transition, card, candidates, target_category)

    def pick_transition(self, card: Card, candidates: list[dict], target_category: str) -> None:
        def done(tid: str | None) -> None:
            if tid:
                self.execute_transition(card, tid, target_category)
            else:
                self.cancel_move(card)
        self.push_screen(TransitionPicker(card.issue, candidates), done)

    @work(thread=True)
    def execute_transition(self, card: Card, transition_id: str, target_category: str) -> None:
        key = card.issue.key
        try:
            self.jira.do_transition(key, transition_id)
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(self.notify, t("transition_failed", key=key, error=e),
                                  severity="error")
            self.call_from_thread(self.cancel_move, card)
            return
        self.call_from_thread(self.notify, t("moved", key=key))
        self.call_from_thread(self.action_refresh)

    # ---- session launch / misc

    def action_launch(self) -> None:
        card = self.focused_card()
        if not card:
            return
        key = card.issue.key
        if key in self._launching:
            self.notify(t("launching_already", key=key))
            return
        pane = self.sessions.get(key)
        if pane and pane not in agent_statuses():
            # The recorded pane is gone -> drop the mapping
            del self.sessions[key]
            save_sessions(self.sessions)
            pane = None
        if not pane and (pane := find_session_pane(key)):
            # Re-associate if the mapping was lost but the issue's agent is alive
            self.sessions[key] = pane
            save_sessions(self.sessions)
        if pane:
            self.focus_session(key, pane)
            return
        self._launching.add(key)
        self.notify(t("launching", key=key))
        self.run_launch(card.issue)

    @work(thread=True)
    def focus_session(self, key: str, pane: str) -> None:
        """Focus the tab of an existing session."""
        try:
            tab_id = find_key(herdr("pane", "get", pane), "tab_id")
            if not tab_id:
                raise RuntimeError(t("no_tab_id", pane=pane))
            herdr("tab", "focus", str(tab_id))
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(
                self.notify, t("focus_failed", key=key, error=e), severity="error")

    @work(thread=True)
    def run_launch(self, issue: Issue) -> None:
        try:
            pane = launch_claude(issue, self.cfg)
        except Exception as e:  # noqa: BLE001
            self.call_from_thread(self.notify, t("launch_failed", error=e), severity="error")
            return
        finally:
            self._launching.discard(issue.key)
        self.sessions[issue.key] = pane
        save_sessions(self.sessions)
        self.call_from_thread(self.notify, t("launched", key=issue.key))
        self.update_badges()

    def action_open_browser(self) -> None:
        card = self.focused_card()
        if card:
            webbrowser.open(f"{self.cfg.site}/browse/{card.issue.key}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        Config.load()
        print("config OK")
        sys.exit(0)
    BoardApp().run()
