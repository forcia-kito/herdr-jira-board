# herdr-jira-board

Jira のボードをカンバン TUI として [herdr](https://herdr.dev) 内に表示し、
カードから [Claude Code](https://claude.com/claude-code) セッションを起動できる
herdr プラグイン。セッションの状態バッジが看板上でライブ更新されます。

English version: [README.md](README.md)

## 機能

- JQL で取得した課題をステータスカテゴリ3列 (To Do / In Progress / Done) で表示
  — カスタムワークフローのプロジェクトが混在しても破綻しません
- カードは `←` `→` キーまたはドラッグ&ドロップで移動し、`Enter` で確定して
  Jira のトランジションを実行（候補が複数のときは選択ポップアップ）
- カード上で `Enter` すると、その課題を担当する Claude Code セッションを
  新しい herdr タブに起動（`JIRA_ISSUE_KEY` と課題情報の初期プロンプトを注入）
- `herdr agent list` を5秒ごとにポーリングし、カードにセッション状態バッジ
  (working / blocked / idle / done) を表示
- タブ整理アクション（他のタブを閉じる / 右側のタブを閉じる）付き
- UI は英語 / 日本語対応 — システムロケールに追従し、設定で上書きも可能

## 必要なもの

- herdr >= 0.7.5 (macOS / Linux)
- Python 3.11+ **または** [uv](https://docs.astral.sh/uv/)
- Jira Cloud アカウントと API トークン

## インストール

```
herdr plugin install kiitosu/herdr-jira-board
```

これだけです。インストール時に Python 環境を自動で準備します
（uv があれば uv を、なければ専用の仮想環境を使います）。

## 設定

1. https://id.atlassian.com/manage-profile/security/api-tokens で API トークンを
   作成（「スコープ付き」ではなくクラシックな「API トークンを作成」を選択）。
2. [config.toml.example](config.toml.example) をプラグインの設定ディレクトリに
   コピーして編集:

```
cp config.toml.example "$(herdr plugin config-dir jira-board)/config.toml"
```

最小構成:

```toml
site = "https://your-site.atlassian.net"
email = "you@example.com"
api_token = "<API トークン>"
```

すべてのオプション（`api_token_cmd`, `jql`, `language`, `[project_dirs]`）は
`config.toml.example` のコメントを参照してください。

## 使い方

herdr 内で看板を開く:

```
herdr plugin pane open --plugin jira-board --entrypoint board
```

`~/.config/herdr/config.toml` にキーバインドを登録しておくと便利です:

```toml
[[keys.command]]
key = "prefix+k"
type = "plugin_action"
command = "jira-board.open-board"
description = "看板表示"

[[keys.command]]
key = "prefix+x"
type = "plugin_action"
command = "jira-board.close-right-tabs"
description = "右のタブを閉じる"

[[keys.command]]
key = "prefix+shift+x"
type = "plugin_action"
command = "jira-board.close-other-tabs"
description = "他のタブを閉じる"
```

### キー操作

| キー | 動作 |
| --- | --- |
| `↑` `↓` | 前 / 次のカードへフォーカス |
| `←` `→` | 隣の列へ仮移動 |
| `Enter` | 仮移動の確定、または Claude セッション起動 |
| `Esc` | 仮移動の取消 / 選択解除 |
| `r` | 看板を更新 |
| `o` | 課題をブラウザで開く |
| `q` | 終了 |

マウスでカードを列間ドラッグすることもできます（同様に仮移動 → `Enter` で確定）。

## 開発

```
git clone https://github.com/kiitosu/herdr-jira-board
herdr plugin link herdr-jira-board   # 編集が即時反映されます
```

TUI を開かず設定だけ確認: `bin/jira-board --check`

テスト実行:

```
uv run --with "textual>=0.80" --with "httpx>=0.27" --with pytest --with pytest-asyncio -m pytest tests/
```

## ライセンス

[MIT](LICENSE)
