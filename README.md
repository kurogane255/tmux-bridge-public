# tmux-bridge

手元の VS Code の GitHub Copilot（エージェントモード）から、ラボのサーバー上の tmux セッションに
文字を送り、画面とログを読むための MCP サーバー。tmux の中で動いている Claude Code に、
Copilot から指示を出して結果を受け取る用途を想定している。

作業用リポジトリ（非公開）の公開スナップショット。手で写して更新するため、作業用より
遅れることがある。

```
VS Code (Copilot) ──stdio──▶ server.py ──ssh──▶ zero2 / zero7 の tmux
   WSL で動く                   標準ライブラリだけ     load-buffer / paste-buffer / capture-pane
```

## ツール

| ツール | 内容 |
|---|---|
| `list_sessions` | ホスト上の tmux セッションの一覧（tmux サーバー＝ソケットごと） |
| `send` | 文字を貼り付けとして送り、Enter を押す。送る直前のカーソル行を開始マーカーとして残す |
| `read` | 画面の最後の N 行（既定 40、最大 2000） |
| `wait_idle` | 画面が `quiet` 秒間変わらなくなるまで待つ（応答が終わるのを待つ） |
| `log` | 開始マーカーから最後までのターミナルログ。`save=true` で手元のファイルにも保存する |

開始マーカーは tmux のセッションオプション `@tmux_bridge_mark` に行番号を書くだけで、
セッションには何も入力しない。`log` はその行から取り出すので、送った指示と応答の全体を、
画面の外へ流れた分も含めて取り込める。保存先は `~/tmux-bridge-logs/`
（環境変数 `TMUX_BRIDGE_LOG_DIR` で変えられる）。

制約: tmux の履歴が上限（`history-limit`、既定 2000 行）に達すると古い行が消えて
マーカーの位置がずれる。その場合 `log` は注意書きを付けて返す。長い作業を取り込むなら、
サーバー側の `~/.tmux.conf` で `set -g history-limit 50000` などに増やしておく。

cc-tmux が作るセッションは、セッションごとに tmux サーバーを分けている（`tmux -L <名前>`）。
そのため、ソケット名は既定でセッション名と同じとみなす。違う場合は `socket` を渡す。

## 準備

WSL の Ubuntu の中で動かすことを前提にする。VS Code は、Windows の VS Code を WSL に
接続して使っても、Ubuntu に入れた Linux 版を起動して使ってもよい。手順は [docs/setup.md](docs/setup.md) にある。
要点は次の 4 つ。

1. WSL から各ホストへ、パスワード無しで SSH で入れるようにする
2. `git clone https://github.com/kurogane255/tmux-bridge-public.git ~/tmux-bridge` で取得する
3. `~/tmux-bridge/setup/check.sh` を実行し、すべて OK になるまで直す
4. VS Code に [examples/mcp.wsl.json](examples/mcp.wsl.json) の内容を登録する

必要なのは Python 3.9 以上と OpenSSH クライアントだけで、追加のパッケージは要らない。
Windows で直接動かすこともでき、その手順は docs/setup.md の最後にある（未検証）。

## 注意

`send` で送った文字は、受け取る側のプログラムから見ると、ユーザーがキーボードで打った
入力と区別がつかない。tmux の中の Claude Code に送れば、それはユーザー本人の指示として
扱われる。送る前に、何を送るのかを Copilot の画面で確かめること。
