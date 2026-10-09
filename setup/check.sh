#!/usr/bin/env bash
# tmux-bridge の準備ができているかを確かめる（WSL / Linux 用）。
# 設定ファイルが無ければ見本から作り、SSH 鍵が無ければ作るかを尋ねる。
set -u
cfg="${TMUX_BRIDGE_CONFIG:-$HOME/.config/tmux-bridge/config.json}"
here="$(cd "$(dirname "$0")/.." && pwd)"
ng=0
ok()   { echo "  OK   $*"; }
fail() { echo "  NG   $*"; ng=1; }

echo "[1] コマンド"
for c in python3 ssh; do
  command -v "$c" >/dev/null && ok "$c: $(command -v "$c")" || fail "$c が無い"
done

echo "[2] 設定ファイル $cfg"
if [ ! -f "$cfg" ]; then
  mkdir -p "$(dirname "$cfg")"
  cp "$here/config.example.json" "$cfg"
  echo "  作成 見本から作った。hosts を自分の環境に合わせて直すこと"
fi
hosts=$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["hosts"]))' "$cfg") \
  && ok "hosts: $hosts" || { fail "設定ファイルを読めない"; exit 1; }

echo "[3] SSH 鍵"
keys=$(ls ~/.ssh/id_* 2>/dev/null | grep -v '\.pub$' | tr '\n' ' ')
if [ -n "$keys" ]; then
  ok "$keys"
else
  read -r -p "  鍵が無い。~/.ssh/id_ed25519 を作る? [y/N] " a
  if [ "$a" = y ]; then
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
    echo "  各ホストへ公開鍵を置く: ssh-copy-id <host>"
  else
    fail "SSH 鍵が無い"
  fi
fi

echo "[4] 各ホストへの接続と tmux"
for h in $hosts; do
  if out=$(ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR "$h" 'tmux -V' 2>&1); then
    ok "$h: $out"
  else
    fail "$h: $out"
    echo "       パスワード無しで入れない場合は ssh-copy-id $h を実行する"
  fi
done

echo "[5] MCP サーバーの応答"
resp=$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_sessions","arguments":{}}}' \
  | python3 "$here/server.py")
echo "$resp" | python3 -c '
import json, sys
for line in sys.stdin:
    m = json.loads(line); r = m.get("result", {})
    if "content" in r:
        print("  " + ("NG" if r.get("isError") else "OK") + "   既定のホストの tmux セッション:")
        for l in r["content"][0]["text"].splitlines(): print("         " + l)
' || fail "server.py が応答しない"

echo
[ $ng = 0 ] && echo "すべて OK。examples/mcp.wsl.json を VS Code に登録する" || echo "NG の項目を直してから、もう一度実行する"
exit $ng
