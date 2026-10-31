# FlashTrans 2.4.0 一键构建（GPU 改造版）
#
# 用法（在 flashtrans-next 目录下，用 PowerShell）：
#   .\build.ps1            # 默认构建：GGUF 走 CPU，翻译走 CUDA 自动探测，无需 CUDA Toolkit
#   .\build.ps1 -Gpu       # GGUF 也走 CUDA：需本机已安装 CUDA Toolkit 12.x
#
# 前提（首次需自行装好）：
#   - Node.js 18+（含 npm）
#   - Rust 工具链 + MSVC + Windows SDK（cargo tauri build 用）
#   - WebView2 运行时（Win10/11 一般自带）
#   - Python 3.11+（冻结翻译桥接用；脚本会自动建 .venv 并装依赖）
#   - 仅 -Gpu 时需要：CUDA Toolkit 12.x（版本与 llama-cpp-2 编译期望一致）
#   - -Inno：额外用 Inno Setup（ISCC.exe 需在 PATH）打出与原版同名的 FlashTrans-2.4.0-Setup.exe
#
# 重要：模型文件(models)不随安装包分发。安装完成后，把下载的 models 文件夹
#       整体复制到安装目录下（与 FlashTrans.exe、bridge 同级），再在软件设置里添加即可。
param([switch]$Gpu, [switch]$Inno)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot                                  # flashtrans-next\
$repoRoot = Split-Path $root -Parent                   # FlashTrans-master\
Push-Location $root
try {
    # 1) 前端
    Write-Host "==> 1/4 npm install" -ForegroundColor Cyan
    npm install
    Write-Host "==> 2/4 npm run build (tsc + vite)" -ForegroundColor Cyan
    npm run build

    # 2) 冻结翻译桥接 flashtrans-bridge.exe（Python → exe，含 GPU 自动探测逻辑）
    $venv = Join-Path $repoRoot ".venv"
    if (-not (Test-Path $venv)) {
        Write-Host "==> 创建 Python 虚拟环境 $venv" -ForegroundColor Cyan
        python -m venv $venv
    }
    & (Join-Path $venv "Scripts\python.exe") -m pip install -U pip
    & (Join-Path $venv "Scripts\pip.exe") install -r requirements-bridge.txt pyinstaller
    Write-Host "==> 3/4 冻结翻译桥接" -ForegroundColor Cyan
    & (Join-Path $venv "Scripts\python.exe") -m PyInstaller --noconfirm `
        --distpath (Join-Path $root "installer\bridge-dist") `
        --workpath (Join-Path $root "installer\bridge-work") `
        (Join-Path $root "installer\bridge.spec")
    $bridgeExe = Join-Path $root "installer\bridge-dist\flashtrans-bridge\flashtrans-bridge.exe"
    if (-not (Test-Path $bridgeExe)) { throw "桥接产物缺失：$bridgeExe" }

    # 3) 出安装包（Tauri 自带 NSIS 打包，自动产出 *-setup.exe）
    Write-Host "==> 4/4 cargo tauri build$(if($Gpu){' --features cuda'})" -ForegroundColor Cyan
    if ($Gpu) {
        cargo tauri build --features cuda
    } else {
        cargo tauri build
    }
    $nsis = Join-Path $root "src-tauri\target\release\bundle\nsis"
    Write-Host "NSIS 安装包已生成，在：$nsis" -ForegroundColor Green

    # 4)（可选）Inno Setup 还原原版命名 FlashTrans-2.4.0-Setup.exe
    if ($Inno) {
        $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($iscc) {
            Write-Host "==> 5/5 Inno Setup 打包（原版命名）" -ForegroundColor Cyan
            & $iscc.Source (Join-Path $root "installer\FlashTrans.iss")
            Write-Host "Inno 安装包已生成，在：installer\out\" -ForegroundColor Green
        } else {
            Write-Warning "未找到 ISCC.exe（Inno Setup 编译器），跳过 Inno 打包。NSIS 安装包已可用。"
        }
    }

    Write-Host "完成。" -ForegroundColor Green
    Write-Host "提示：安装后请把下载的 models 文件夹复制到安装目录（与 FlashTrans.exe 同级）。" -ForegroundColor Yellow
} finally {
    Pop-Location
}
