<#
启动绒球，监听所有网卡，方便手机访问。

用法：
    .\scripts\serve.ps1

会打印本机局域网地址；手机连同一个 WiFi 即可打开。
第一次运行请在管理员 PowerShell 里执行，以便放行防火墙端口。
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$PORT = 8780
$RULE = "绒球 Rongqiu $PORT"

$isAdmin = ([Security.Principal.WindowsPrincipal](
    [Security.Principal.WindowsIdentity]::GetCurrent())
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

$rule = Get-NetFirewallRule -DisplayName $RULE -ErrorAction SilentlyContinue
if (-not $rule) {
    if ($isAdmin) {
        New-NetFirewallRule -DisplayName $RULE -Direction Inbound -Protocol TCP -LocalPort $PORT -Action Allow -Profile Private,Domain | Out-Null
        Write-Host "已放行防火墙端口 $PORT" -ForegroundColor Green
    } else {
        Write-Host "防火墙未放行。用管理员 PowerShell 再跑一次，手机才能访问。" -ForegroundColor Yellow
    }
}

$python = $null
foreach ($c in @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "..\quant-lab\.venv\Scripts\python.exe"))) {
    if (Test-Path $c) { $python = (Resolve-Path $c).Path; break }
}
if (-not $python) {
    Write-Host "找不到 python 环境（.venv 或 ../quant-lab/.venv）" -ForegroundColor Red
    exit 1
}

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "绒球已启动" -ForegroundColor Green
Write-Host ""
Write-Host ("  本机：  http://127.0.0.1:" + $PORT) -ForegroundColor Cyan
foreach ($ip in $ips) {
    Write-Host ("  手机：  http://" + $ip + ":" + $PORT) -ForegroundColor Cyan
}
Write-Host ""
Write-Host "手机需要连同一个 WiFi。按 Ctrl+C 停止。" -ForegroundColor DarkGray
Write-Host ""

& $python -m uvicorn app.server:app --host 0.0.0.0 --port $PORT --log-level warning
exit $LASTEXITCODE