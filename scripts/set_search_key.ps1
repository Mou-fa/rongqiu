<#
把 Tavily API key 写进 configs\search.yaml，然后自动跑一次检索验证。

用法：
    .\scripts\set_search_key.ps1

key 用隐藏输入读取，不会回显、不会进命令历史。
写进的是 gitignore 里的文件，不会被提交。
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$cfgPath = Join-Path $root "configs\search.yaml"
if (-not (Test-Path $cfgPath)) {
    Write-Host "找不到 configs\search.yaml" -ForegroundColor Red
    exit 1
}

# 找 python：本项目有 .venv 就用它，否则用 quant-lab 的
$python = $null
$candidates = @(
    (Join-Path $root ".venv\Scripts\python.exe"),
    (Join-Path $root "..\quant-lab\.venv\Scripts\python.exe")
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $python = (Resolve-Path $c).Path; break }
}
if (-not $python) {
    Write-Host "找不到 python 环境（.venv 或 ../quant-lab/.venv）" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "把 Tavily key 粘贴进来，回车确认（输入不回显）" -ForegroundColor Cyan
Write-Host "格式形如 tvly-xxxxxxxxxxxxxxxx" -ForegroundColor DarkGray
$secure = Read-Host "API key" -AsSecureString
$key = [System.Net.NetworkCredential]::new("", $secure).Password

if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "没输入内容，已取消。" -ForegroundColor Yellow
    exit 1
}
$key = $key.Trim()
if (-not $key.StartsWith("tvly-")) {
    Write-Host "这个 key 不是 tvly- 开头，可能粘贴错了。已取消。" -ForegroundColor Yellow
    exit 1
}

$lines = Get-Content $cfgPath -Encoding UTF8
$out = foreach ($line in $lines) {
    if ($line -match '^\s*api_key\s*:') {
        'api_key: "' + $key + '"'
    } else {
        $line
    }
}
$out | Set-Content $cfgPath -Encoding UTF8

Write-Host ""
Write-Host "已写入 configs\search.yaml（这个文件在 .gitignore 里，不会被提交）" -ForegroundColor Green
Write-Host "python: $python" -ForegroundColor DarkGray
Write-Host ""
Write-Host "现在跑一次真实检索验证..." -ForegroundColor Cyan
Write-Host ("-" * 60)
& $python (Join-Path $root "scripts\check_search.py")
$code = $LASTEXITCODE
Write-Host ("-" * 60)
if ($code -eq 0) {
    Write-Host "搜索接通了。" -ForegroundColor Green
    Write-Host "界面：http://127.0.0.1:8780" -ForegroundColor Cyan
} else {
    Write-Host "验证没通过，看上面的输出。" -ForegroundColor Red
}
exit $code
