# Copilot から使う

Copilot Chat をエージェントモードにして、普段の言葉で頼めばよい。Copilot が tmux-bridge の
ツールを選んで呼ぶ。ツールを呼ぶたびに VS Code が確認を求めるので、`send` の中身は
そこで確かめてから許可する。

## 頼み方の例

- 「zero2 の tmux セッションの一覧を出して」→ `list_sessions`
- 「zero2 の setup セッションの画面を読んで」→ `read`
- 「setup セッションの Claude に『クラスタの状態を確認して』と送って、終わるまで待って、
  結果をまとめて」→ `send` → `wait_idle` → `log`
- 「さっきの作業のログを保存して」→ `log`（`save=true`）

## 指示から取り込みまでの流れ

1. `send` が、送る直前のカーソル行を開始マーカーとして残し、文字を貼り付けて Enter を押す
2. `wait_idle` が、画面が一定時間（既定 5 秒）変わらなくなるまで待つ。
   Claude Code が長く考える場合は `quiet` を 15〜30 に、`timeout` を 600 などに増やす
3. `log` が、マーカーの行から最後までを返す。送った指示と応答の全体が入る

`wait_idle` は画面が止まったことしか分からない。Claude Code が確認を求めて止まって
いる場合も「終わった」と判断する。`log` の最後を読んで、確認待ちなら `send` で答える。

## Copilot に覚えさせておくとよいこと

`.github/copilot-instructions.md` に次のように書いておくと、頼み方を短くできる。

```markdown
## tmux-bridge
- ラボのサーバーの Claude Code へ指示を出すときは tmux-bridge を使う
- 送ったら wait_idle（quiet=15, timeout=600）で待ち、log で結果を取り込んでから要約する
- send で送る文字は、受け取った Claude Code にとってユーザー本人の指示になる。
  削除や停止のような取り消せない指示は、送る前に私に確認する
```
