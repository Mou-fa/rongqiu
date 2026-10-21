# 构建 Windows 桌面版（PyInstaller + 内嵌 WebView2 窗口）。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\build_app.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\quant-lab\.venv\Scripts\python.exe"
$Csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$Icon = Join-Path $Root "app\static\favicon.ico"

# ---------- 1. PyInstaller：Python 服务端 ----------
$pyArgs = @(
  "-m", "PyInstaller",
  "--noconfirm", "--clean", "--windowed",
  "--name", "Rongqiu",
  "--paths", ".",
  "--add-data", "app/static;app/static",
  "--add-data", "configs/questions.yaml;configs",
  "--add-data", "configs/taxonomy.yaml;configs",
  "--add-data", "configs/soundscape.yaml;configs",
  "--add-data", "configs/surfaces.jsonl;configs",
  "--add-data", "configs/lexicon.jsonl;configs",
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

# ---------- 2. WebView2 SDK（第一次构建时下载，之后复用） ----------
$Vendor = Join-Path $Root "vendor\webview2"
$Sdk = Join-Path $Vendor "sdk"
$CoreDll = Join-Path $Sdk "lib\net462\Microsoft.Web.WebView2.Core.dll"
if (-not (Test-Path $CoreDll)) {
  $ver = "1.0.4258.31"
  New-Item -ItemType Directory -Force -Path $Vendor | Out-Null
  $pkg = Join-Path $Vendor "microsoft.web.webview2.$ver.nupkg"
  if (-not (Test-Path $pkg)) {
    Write-Host "下载 WebView2 SDK $ver ..."
    Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$ver/microsoft.web.webview2.$ver.nupkg" -OutFile $pkg -TimeoutSec 180
  }
  $zip = "$pkg.zip"
  Copy-Item $pkg $zip -Force
  Expand-Archive -Path $zip -DestinationPath $Sdk -Force
  Remove-Item $zip -Force
}

# ---------- 3. 编译内嵌窗口宿主 ----------
$Out = Join-Path $Root "dist\Rongqiu"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Copy-Item (Join-Path $Sdk "lib\net462\Microsoft.Web.WebView2.Core.dll") $Out -Force
Copy-Item (Join-Path $Sdk "lib\net462\Microsoft.Web.WebView2.WinForms.dll") $Out -Force
Copy-Item (Join-Path $Sdk "runtimes\win-x64\native\WebView2Loader.dll") $Out -Force
$cscArgs = @(
  "/nologo", "/target:winexe", "/platform:x64",
  "/out:$Out\RongqiuWindow.exe",
  "/reference:System.dll", "/reference:System.Core.dll",
  "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
  "/reference:$Out\Microsoft.Web.WebView2.Core.dll",
  "/reference:$Out\Microsoft.Web.WebView2.WinForms.dll",
  "tools\RongqiuWindow.cs"
)
& $Csc @cscArgs

Write-Host "构建完成：dist\Rongqiu\Rongqiu.exe"
