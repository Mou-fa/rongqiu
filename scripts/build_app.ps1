# 构建 Windows 桌面版（PyInstaller 文件夹版）。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-lab\.venv\Scripts\python.exe"
$Icon = Join-Path $Root "app\static\favicon.ico"

$pyArgs = @(
  "-m", "PyInstaller",
  "--noconfirm", "--clean", "--windowed",
  "--name", "Rongqiu",
  "--paths", ".",
  "--add-data", "app/static;app/static",
  "--add-data", "configs/questions.yaml;configs",
  "--add-data", "configs/taxonomy.yaml;configs",
  "--add-data", "configs/soundscape.yaml;configs",
  "--add-data", "configs/llm.example.yaml;configs",
  "--add-data", "configs/search.example.yaml;configs",
  "--add-data", "data/triple_index.json;data",
  "--add-data", "data/local_corpus.json;data",
  "--collect-all", "uvicorn",
  "--hidden-import", "psutil"
)
if (Test-Path $Icon) { $pyArgs += @("--icon", $Icon) }
$pyArgs += "launcher.py"

& $Py @pyArgs
Write-Host "构建完成：dist\Rongqiu\Rongqiu.exe"
