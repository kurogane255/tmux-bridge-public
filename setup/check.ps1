# tmux-bridge の準備ができているかを確かめる（Windows ネイティブ用）。
# 使い方: powershell -ExecutionPolicy Bypass -File setup\check.ps1
# 設定ファイルが無ければ見本から作り、SSH 鍵が無ければ作るかを尋ねる。
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$here = Split-Path -Parent $PSScriptRoot
$cfg = if ($env:TMUX_BRIDGE_CONFIG) { $env:TMUX_BRIDGE_CONFIG } else { Join-Path $HOME ".config\tmux-bridge\config.json" }
$script:ng = $false
function Ok($m)   { Write-Host "  OK   $m" }
function Fail($m) { Write-Host "  NG   $m" -ForegroundColor Red; $script:ng = $true }

Write-Host "[1] コマンド"
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py -and ($py.Source -notlike "*WindowsApps*")) { Ok "python: $($py.Source)" }
else { Fail "python が無い（Microsoft Store の仮のコマンドは使えない）。https://www.python.org/ から入れる" }
$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if ($ssh) { Ok "ssh: $($ssh.Source)" }
else { Fail "ssh が無い。設定 > システム > オプション機能 で OpenSSH クライアントを追加する" }

Write-Host "[2] 設定ファイル $cfg"
if (-not (Test-Path $cfg)) {
  New-Item -ItemType Directory -Force (Split-Path $cfg) | Out-Null
  Copy-Item (Join-Path $here "config.example.json") $cfg
  Write-Host "  作成 見本から作った。hosts を自分の環境に合わせて直すこと"
}
try { $hosts = (Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json).hosts; Ok "hosts: $($hosts -join ' ')" }
catch { Fail "設定ファイルを読めない"; exit 1 }

Write-Host "[3] SSH 鍵"
$keys = Get-ChildItem (Join-Path $HOME ".ssh\id_*") -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "*.pub" }
if ($keys) { Ok ($keys.Name -join " ") }
else {
  $a = Read-Host "  鍵が無い。~\.ssh\id_ed25519 を作る? [y/N]"
  if ($a -eq "y") {
    ssh-keygen -t ed25519 -f (Join-Path $HOME ".ssh\id_ed25519")
    Write-Host "  各ホストへ公開鍵を置く（Windows には ssh-copy-id が無い）:"
    Write-Host '    type $HOME\.ssh\id_ed25519.pub | ssh <host> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"'
  } else { Fail "SSH 鍵が無い" }
}

Write-Host "[4] 各ホストへの接続と tmux"
foreach ($h in $hosts) {
  $out = & ssh -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR $h "tmux -V" 2>&1
  if ($LASTEXITCODE -eq 0) { Ok "${h}: $out" }
  else { Fail "${h}: $out"; Write-Host "       パスワード無しで入れない場合は、[3] の方法で公開鍵を置く" }
}

Write-Host "[5] MCP サーバーの応答"
if ($py) {
  $req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' + "`n" +
         '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_sessions","arguments":{}}}' + "`n"
  $OutputEncoding = [Text.Encoding]::UTF8
  $resp = $req | & python (Join-Path $here "server.py")
  foreach ($line in $resp) {
    $m = $line | ConvertFrom-Json
    if ($m.result.content) {
      $tag = if ($m.result.isError) { "NG" } else { "OK" }
      if ($m.result.isError) { $script:ng = $true }
      Write-Host "  $tag   既定のホストの tmux セッション:"
      $m.result.content[0].text -split "`n" | ForEach-Object { Write-Host "         $_" }
    }
  }
}

Write-Host ""
if ($script:ng) { Write-Host "NG の項目を直してから、もう一度実行する"; exit 1 }
Write-Host "すべて OK。examples\mcp.windows.json を VS Code に登録する"
