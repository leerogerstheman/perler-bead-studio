param(
    [string]$Source = "$env:USERPROFILE\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python",
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$target = Join-Path $root 'python'

function Info($msg) { if (-not $Quiet) { Write-Host $msg } }

if (-not (Test-Path -LiteralPath (Join-Path $Source 'python.exe'))) {
    Write-Host "[错误] 在下面的位置没找到 python.exe：$Source" -ForegroundColor Red
    Write-Host "可以用 -Source 参数指定一个可用的 Python 安装目录。"
    exit 1
}

Info "[1/4] 清理旧目录 ..."
if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }

Info "[2/4] 复制 Python 运行时（约 166 MB，请稍等）..."
New-Item -ItemType Directory -Path $target | Out-Null
robocopy $Source $target /E /NFL /NDL /NJH /NJS /NP /XF *.pdb | Out-Null

Info "[3/4] 验证能否 import tkinter 和 Pillow ..."
$exe = Join-Path $target 'python.exe'
$out = & $exe -c "import tkinter, PIL; from PIL import Image, ImageTk; print('OK', PIL.__version__)" 2>&1
if ($LASTEXITCODE -ne 0 -or "$out" -notmatch 'OK') {
    Write-Host "[失败] 本地运行时不能正常工作：$out" -ForegroundColor Red
    exit 1
}
Info "      $out"

Info "[4/4] 清理缓存 ..."
Get-ChildItem -LiteralPath $target -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$size = (Get-ChildItem -LiteralPath $target -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("完成：本地运行时已就绪（{0:N0} MB）。现在双击 启动.bat 即可运行。" -f ($size / 1MB)) -ForegroundColor Green
