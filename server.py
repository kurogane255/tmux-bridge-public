#!/usr/bin/env python3
"""tmux-bridge: an MCP server (stdio) that drives tmux sessions on remote hosts over SSH.

Meant to run in WSL and be registered with VS Code's GitHub Copilot (agent mode), so that
Copilot can type into Claude Code sessions running in tmux on lab servers and read the screen.
Standard library only, so nothing has to be installed in WSL.

Tools
  list_sessions(host)                          tmux sessions on the host, per tmux server (socket)
  send(host, session, text, enter=True)        type text (as a paste) and press Enter
  read(host, session, lines=40)                the last lines of the screen
  wait_idle(host, session, timeout=180, quiet=5)  wait until the screen stops changing
  log(host, session, save=False)               everything from the start marker that the last
                                               send left, to the end (optionally saved to a file)

Start marker: send() records the absolute line where the cursor was, in the tmux session option
@tmux_bridge_mark. Nothing is typed into the session. log() captures from that line, so the
answer to the last instruction can be taken in whole even after it scrolled off the screen.

Configuration: ~/.config/tmux-bridge/config.json (see config.example.json)
  {"hosts": ["zero2", "zero7"], "default_host": "zero2"}
Hosts are SSH names (~/.ssh/config). Only listed hosts can be used.

Sessions started by cc-tmux use one tmux server per session (`tmux -L <name>`), so by default
the socket name is the session name. Pass "socket" to override.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime

PROTOCOL_VERSION = "2025-06-18"
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR"]
LOG_DIR = os.path.expanduser(os.environ.get("TMUX_BRIDGE_LOG_DIR", "~/tmux-bridge-logs"))
MARK = "@tmux_bridge_mark"
CONFIG_PATH = os.path.expanduser(os.environ.get("TMUX_BRIDGE_CONFIG", "~/.config/tmux-bridge/config.json"))


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {}
    hosts = cfg.get("hosts") or [h for h in os.environ.get("TMUX_BRIDGE_HOSTS", "").split(",") if h]
    return {"hosts": hosts, "default_host": cfg.get("default_host") or (hosts[0] if hosts else None)}


class ToolError(Exception):
    pass


def check_name(kind: str, value: str) -> str:
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ToolError(f"{kind} の名前が不正: {value!r}（英数字と . _ - だけ、64 文字まで）")
    return value


def pick_host(args: dict) -> str:
    cfg = load_config()
    host = args.get("host") or cfg["default_host"]
    if not host:
        raise ToolError(f"host が無い。{CONFIG_PATH} の hosts を設定すること")
    if host not in cfg["hosts"]:
        raise ToolError(f"host {host!r} は許可されていない（許可: {cfg['hosts']}）")
    return check_name("host", host)


def remote(host: str, script: str, stdin: str = "", timeout: int = 30) -> str:
    """Run a bash script on the host. ssh joins its arguments into one command line for the
    remote shell, so the script is quoted as a whole. The text to paste never goes into the
    command line: it comes on stdin. Names in the script are checked by NAME_RE beforehand."""
    r = subprocess.run([*SSH, host, "bash -c " + shlex.quote(script)], input=stdin,
                       capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise ToolError(f"{host}: 終了コード {r.returncode}: {(r.stderr or r.stdout).strip()[:500]}")
    return r.stdout


def target(args: dict) -> tuple[str, str, str]:
    host = pick_host(args)
    session = check_name("session", args.get("session", ""))
    sock = check_name("socket", args.get("socket") or session)
    return host, session, sock


def t_list_sessions(args: dict) -> str:
    host = pick_host(args)
    out = remote(host, r'''
d="${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)"
for s in "$d"/*; do
  [ -S "$s" ] || continue
  n=${s##*/}
  # 使われていないソケットが残っていることがあるので、失敗は無視する
  tmux -L "$n" list-sessions -F "$n #{session_name} #{session_windows}w #{?session_attached,attached,detached}" 2>/dev/null || true
done
exit 0''')
    return out.strip() or "（tmux のセッションは無い）"


def t_send(args: dict) -> str:
    host, session, sock = target(args)
    text = args.get("text", "")
    if not isinstance(text, str) or not text:
        raise ToolError("text が空")
    if len(text) > 20000:
        raise ToolError("text が長すぎる（20000 文字まで）")
    enter = args.get("enter", True)
    # 貼り付ける前のカーソル行（履歴の先頭から数えた行番号）を開始マーカーとして残す
    script = f'''set -e
tmux -L {sock} has-session -t {session}
mark=$(tmux -L {sock} display-message -p -t {session} '#{{e|+:#{{history_size}},#{{cursor_y}}}}')
tmux -L {sock} set-option -t {session} {MARK} "$mark"
tmux -L {sock} load-buffer -b tmux-bridge -
tmux -L {sock} paste-buffer -p -d -b tmux-bridge -t {session}
''' + (f'sleep 0.3; tmux -L {sock} send-keys -t {session} Enter\n' if enter else '')
    remote(host, script, stdin=text)
    return f"{host}:{session} に {len(text)} 文字を送った" + ("（Enter あり）" if enter else "（Enter なし）")


def capture(host: str, session: str, sock: str, lines: int) -> str:
    out = remote(host, f"tmux -L {sock} capture-pane -p -J -t {session} -S -{lines}")
    return "\n".join(out.rstrip("\n").splitlines()[-lines:])


def t_read(args: dict) -> str:
    host, session, sock = target(args)
    lines = int(args.get("lines", 40))
    if not 1 <= lines <= 2000:
        raise ToolError("lines は 1〜2000")
    return capture(host, session, sock, lines)


def t_log(args: dict) -> str:
    host, session, sock = target(args)
    out = remote(host, f'''set -e
mark=$(tmux -L {sock} show-options -v -t {session} {MARK} 2>/dev/null || true)
[ -n "$mark" ] || {{ echo "開始マーカーが無い。先に send を使うこと" >&2; exit 3; }}
set -- $(tmux -L {sock} display-message -p -t {session} '#{{history_size}} #{{history_limit}}')
start=$((mark - $1))
# 履歴が上限に達していると古い行が消え、マーカーの位置がずれる
if [ "$1" -ge "$2" ]; then echo "TRUNCATED"; else echo "OK"; fi
[ "$start" -lt "-$1" ] && start="-"
tmux -L {sock} capture-pane -p -J -t {session} -S "$start"
''', timeout=60)
    status, _, body = out.partition("\n")
    body = body.rstrip()
    note = ("（注意: 履歴が上限に達していたので、先頭がずれているか欠けている可能性がある）\n"
            if status == "TRUNCATED" else "")
    n = len(body.splitlines())
    if args.get("save"):
        os.makedirs(LOG_DIR, exist_ok=True)
        path = os.path.join(LOG_DIR, f"{host}_{session}_{datetime.now():%Y%m%d-%H%M%S}.log")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body + "\n")
        tail = "\n".join(body.splitlines()[-40:])
        return f"{note}{n} 行を {path} に保存した。最後の 40 行:\n{tail}"
    if n > 3000:
        body = "\n".join(body.splitlines()[-3000:])
        note += f"（{n} 行のうち最後の 3000 行だけを返す。全部ほしいときは save=true）\n"
    return f"{note}開始マーカーから {n} 行:\n{body}"


def t_wait_idle(args: dict) -> str:
    host, session, sock = target(args)
    timeout = int(args.get("timeout", 180))
    quiet = int(args.get("quiet", 5))
    start = time.time()
    last, since = None, time.time()
    while time.time() - start < timeout:
        now = capture(host, session, sock, 60)
        if now != last:
            last, since = now, time.time()
        elif time.time() - since >= quiet:
            tail = "\n".join(now.splitlines()[-40:])
            return f"{quiet} 秒間、画面が変わらなかった（{int(time.time() - start)} 秒待った）。最後の 40 行:\n{tail}"
        time.sleep(1)
    tail = "\n".join((last or "").splitlines()[-40:])
    return f"{timeout} 秒たっても画面が変わり続けている。最後の 40 行:\n{tail}"


S = {"type": "string"}
TOOLS = {
    "list_sessions": (t_list_sessions, "List tmux sessions (per tmux server/socket) on a lab host.",
                      {"type": "object", "properties": {"host": S}}),
    "send": (t_send, "Type text into a tmux session as a paste, then press Enter. The receiving program "
                     "(e.g. Claude Code) treats it as the user's own input.",
             {"type": "object", "required": ["session", "text"], "properties": {
                 "host": S, "session": S, "socket": S, "text": S, "enter": {"type": "boolean"}}}),
    "read": (t_read, "Read the last lines of a tmux session's screen.",
             {"type": "object", "required": ["session"], "properties": {
                 "host": S, "session": S, "socket": S, "lines": {"type": "integer"}}}),
    "wait_idle": (t_wait_idle, "Wait until the session's screen stops changing (the program finished "
                               "answering), then return the last 40 lines.",
                  {"type": "object", "required": ["session"], "properties": {
                      "host": S, "session": S, "socket": S,
                      "timeout": {"type": "integer"}, "quiet": {"type": "integer"}}}),
    "log": (t_log, "Return the terminal log from the start marker left by the last send to the end, i.e. "
                   "the instruction and the whole answer. save=true also writes it to a local file.",
            {"type": "object", "required": ["session"], "properties": {
                "host": S, "session": S, "socket": S, "save": {"type": "boolean"}}}),
}


def handle(msg: dict):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "tmux-bridge", "version": "0.1.0"}}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
    if method == "tools/call":
        p = msg.get("params", {})
        name, args = p.get("name"), p.get("arguments") or {}
        if name not in TOOLS:
            return {"content": [{"type": "text", "text": f"不明なツール: {name}"}], "isError": True}
        try:
            text = TOOLS[name][0](args)
            return {"content": [{"type": "text", "text": text}]}
        except (ToolError, subprocess.TimeoutExpired, ValueError) as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    if method == "ping":
        return {}
    if mid is None:
        return None  # notification
    raise KeyError(method)


def main() -> None:
    # Windows の Python は標準入出力を cp932 などで扱うことがあるので、UTF-8 にそろえる
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        try:
            result = handle(msg)
            if mid is None:
                continue
            resp = {"jsonrpc": "2.0", "id": mid, "result": result}
        except KeyError as e:
            resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {e}"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
