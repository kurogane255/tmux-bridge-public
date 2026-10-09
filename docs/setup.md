# 設定方法

手元の PC で tmux-bridge を使えるようにするまでの手順。WSL で動かすことを前提にする。

- WSL（Ubuntu）が入っていて、起動できること
- VS Code は、WSL の Ubuntu の中で server.py を起動できる状態で使う。次のどちらでもよい
  - A: Windows の VS Code を WSL に接続する。WSL のターミナルで `code .` を実行するか、
    左下の「><」から「WSL への接続」を選ぶ。拡張機能「WSL」が要る
  - B: Ubuntu に Linux 版の VS Code を入れて、WSL の中で起動する（画面は WSLg で出る）
- どちらでも、server.py も SSH も Ubuntu の中で動き、Ubuntu の `~/.ssh` を使う

以下のコマンドは、特に書いていなければすべて WSL のターミナルで実行する。

## 1. 必要なものを入れる

Ubuntu なら、Python 3 と OpenSSH クライアントは最初から入っている。無ければ入れる。

```bash
sudo apt install -y python3 openssh-client git
```

## 2. SSH で各ホストへパスワード無しに入れるようにする

すでに `ssh zero2 true` がパスワードを聞かずに終わるなら、この節は飛ばしてよい。

### 鍵を作る

```bash
ssh-keygen -t ed25519
```

パスフレーズは空にしておくのが簡単。tmux-bridge は SSH をパスワード入力なしで実行する
（`BatchMode=yes`）ので、パスフレーズを付けた鍵は ssh-agent に登録しておかないと使えない。
VS Code が起動した server.py は、ターミナルで起動した ssh-agent を引き継がないことがある。
パスフレーズを付けるなら `keychain` などで、どのプロセスからも同じ ssh-agent を使えるようにする。

### ホストを ~/.ssh/config に書く

```
Host zero2
    HostName 192.168.1.12      # ホストの IP か名前
    User you                   # ホスト側のユーザー名
Host zero7
    HostName 192.168.1.17
    User you
```

家の外から tailnet 経由で入る場合は、`HostName` を Tailscale の名前か IP にする。

### 公開鍵を各ホストに置く

```bash
ssh-copy-id zero2
ssh-copy-id zero7
```

初回はホストの鍵を確かめる質問が出るので `yes` と答える。この質問に一度も答えて
いないホストには、server.py から接続できない。

最後に、パスワードを聞かれずに終わることを確かめる。

```bash
ssh zero2 true
ssh zero7 true
```

## 3. リポジトリを取得する

```bash
git clone https://github.com/kurogane255/tmux-bridge-public.git ~/tmux-bridge
```

## 4. 確認スクリプトを実行する

```bash
~/tmux-bridge/setup/check.sh
```

次を順に調べる。

1. `python3` と `ssh` があるか
2. 設定ファイル `~/.config/tmux-bridge/config.json` を読めるか。無ければ見本から作る
3. SSH の鍵があるか。無ければ作るかを尋ねる
4. 各ホストへパスワード無しで入れて、tmux があるか
5. server.py が応答し、既定のホストの tmux セッションの一覧を返すか

すべて `OK` になれば準備はできている。`NG` が出たら、その行の説明に従って直し、
もう一度実行する。

### 設定ファイルの中身

```json
{
  "hosts": ["zero2", "zero7"],
  "default_host": "zero2"
}
```

| 項目 | 意味 |
|---|---|
| `hosts` | 使ってよいホスト。`~/.ssh/config` の `Host` の名前を書く。ここに無いホストは server.py が拒否する |
| `default_host` | ツールの呼び出しでホストを省いたときに使うホスト |

置き場所を変えたいときは、環境変数 `TMUX_BRIDGE_CONFIG` にファイルのパスを入れる。
`log` の保存先は既定で `~/tmux-bridge-logs/` で、環境変数 `TMUX_BRIDGE_LOG_DIR` で変えられる。

## 5. VS Code に登録する

VS Code のコマンドパレット（Ctrl+Shift+P）から、登録先を開く。

| 使う範囲 | A: Windows の VS Code を WSL に接続 | B: Ubuntu の中の VS Code |
|---|---|---|
| すべてのフォルダー | 「MCP: Open Remote User Configuration」 | 「MCP: Open User Configuration」 |
| 1 つのフォルダーだけ | そのフォルダーに `.vscode/mcp.json` を作る | 同じ |

次の内容を書く（[examples/mcp.wsl.json](../examples/mcp.wsl.json) と同じ）。`USER` は
WSL のユーザー名に直す。`~` は使えないので、フルパスで書く。

```json
{
  "servers": {
    "tmux-bridge": {
      "type": "stdio",
      "command": "python3",
      "args": ["/home/USER/tmux-bridge/server.py"]
    }
  }
}
```

すでに他の MCP サーバーを登録している場合は、`servers` の中に `"tmux-bridge": {...}` を
足す。

A の場合、「MCP: Open User Configuration」（Remote が付かないほう）に書くと、
Windows 側で `python3` を探して失敗する。A では Remote のほうに書く。

### 起動して確かめる

1. 保存すると、ファイルの `tmux-bridge` の上に「Start」が出るので押す
   （コマンドパレットの「MCP: List Servers」からも起動できる）
2. Copilot Chat を開き、モードを「Agent」にする
3. 入力欄のツールのボタンを押し、tmux-bridge の 5 つのツールが出ていて、
   チェックが入っていることを確かめる
4. 「zero2 の tmux セッションの一覧を出して」と頼み、一覧が返ってくれば完了

うまく動かないときは、「MCP: List Servers」で tmux-bridge を選び「Show Output」を開くと、
server.py の起動の様子とエラーが見られる。

使い方は [copilot.md](copilot.md) にある。

## 6. サーバー側の設定（任意）

`log` は tmux の履歴から取り出すので、履歴の上限（既定 2000 行）を超える長い作業は、
最初のほうが欠ける。長い作業を取り込むなら、各ホストの `~/.tmux.conf` に書いておく。

```
set -g history-limit 50000
```

この設定が効くのは、新しく作るウィンドウからである。いま動いている cc-tmux のセッション
には効かないので、セッションを作り直すまでは 2000 行のままになる。

## よくある失敗

| 症状 | 原因と対処 |
|---|---|
| `終了コード 255: Permission denied` | 公開鍵がホストに無い。2 の「公開鍵を各ホストに置く」をやる |
| `終了コード 255: Host key verification failed` | ホストの鍵を確かめる質問に答えていない。ターミナルで一度 `ssh zero2` を実行して `yes` と答える |
| `host 'xxx' は許可されていない` | 設定ファイルの `hosts` にそのホストが無い |
| `終了コード 1: can't find session` または `no server running` | セッション名が違うか、ソケット名がセッション名と違う。`list_sessions` の 1 列目がソケット名、2 列目がセッション名なので、違う場合は `socket` も渡す |
| `開始マーカーが無い` | そのセッションに tmux-bridge の `send` で一度も送っていない。`log` は `send` の後に使う |
| VS Code でツールが出ない | 「MCP: List Servers」で tmux-bridge が起動しているかを見る。止まっていれば「Show Output」でエラーを読む |
| 起動時に `python3` が見つからない | A（Windows の VS Code を WSL に接続）で、「MCP: Open User Configuration」（Windows 側）に書いている。「MCP: Open Remote User Configuration」に移す |

## 付録: Windows で直接動かす場合（未検証）

WSL を使わない場合の手順。ここは試していない。

1. PowerShell で Python と Git を入れる。`python` と打って Microsoft Store が開く場合は、
   「設定 > アプリ > アプリの詳細設定 > アプリ実行エイリアス」で `python.exe` をオフにする

   ```powershell
   winget install Python.Python.3.12
   winget install Git.Git
   ```

2. 鍵は `ssh-keygen -t ed25519` で作り、`C:\Users\<名前>\.ssh\config` にホストを書く。
   Windows には `ssh-copy-id` が無いので、公開鍵は次のように置く

   ```powershell
   type $HOME\.ssh\id_ed25519.pub | ssh zero2 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
   ```

3. 取得して確認スクリプトを実行する

   ```powershell
   git clone https://github.com/kurogane255/tmux-bridge-public.git $HOME\tmux-bridge
   powershell -ExecutionPolicy Bypass -File $HOME\tmux-bridge\setup\check.ps1
   ```

4. 「MCP: Open User Configuration」に [examples/mcp.windows.json](../examples/mcp.windows.json)
   の内容を書く
