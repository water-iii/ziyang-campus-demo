param(
    [switch]$NoBrowser,
    [switch]$SmokeTest
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$viteEntry = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$logDir = Join-Path $projectRoot 'logs'
$backendProcess = $null
$frontendProcess = $null

function Test-PortInUse([int]$Port) {
    return [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners().Port -contains $Port
}

function Wait-Http([string]$Uri, [int]$Attempts = 40) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) { return $true }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Show-LogTail([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        Write-Host "`n--- $Path ---" -ForegroundColor Yellow
        Get-Content -LiteralPath $Path -Tail 30
    }
}

try {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw "未找到项目虚拟环境：$pythonExe`n请先按 README_运行手册.md 完成首次安装。"
    }
    if (-not (Test-Path -LiteralPath $viteEntry)) {
        throw "未找到前端依赖。请先运行：Set-Location .\frontend; npm install"
    }
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) { throw '未找到 Node.js，请安装 Node.js 20 或更高版本。' }
    if (Test-PortInUse 8001) { throw '端口 8001 已被占用。请关闭旧后端进程后重试。' }
    if (Test-PortInUse 5173) { throw '端口 5173 已被占用。请关闭旧前端进程后重试。' }

    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $backendOut = Join-Path $logDir 'backend.out.log'
    $backendErr = Join-Path $logDir 'backend.err.log'
    $frontendOut = Join-Path $logDir 'frontend.out.log'
    $frontendErr = Join-Path $logDir 'frontend.err.log'
    foreach ($log in @($backendOut, $backendErr, $frontendOut, $frontendErr)) {
        Set-Content -LiteralPath $log -Value '' -Encoding UTF8
    }

    Write-Host '正在启动午点通后端（8001）…' -ForegroundColor Cyan
    $backendProcess = Start-Process -FilePath $pythonExe `
        -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8001') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr

    Write-Host '正在启动 React 前端（5173）…' -ForegroundColor Cyan
    $frontendProcess = Start-Process -FilePath $nodeCommand.Source `
        -ArgumentList @($viteEntry, '--host', '127.0.0.1', '--port', '5173') `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr

    $backendReady = Wait-Http 'http://127.0.0.1:8001/api/health'
    $frontendReady = Wait-Http 'http://127.0.0.1:5173/'
    if (-not $backendReady -or -not $frontendReady) {
        Show-LogTail $backendErr
        Show-LogTail $frontendErr
        throw "启动超时：backend=$backendReady, frontend=$frontendReady"
    }

    Write-Host ''
    Write-Host '午点通 Demo 已启动成功。' -ForegroundColor Green
    Write-Host '前端：http://127.0.0.1:5173'
    Write-Host 'API ：http://127.0.0.1:8001/docs'
    Write-Host "日志：$logDir"

    if ($SmokeTest) {
        Write-Host '无浏览器冒烟检查完成，正在关闭测试进程。' -ForegroundColor Green
    } else {
        if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:5173' }
        Write-Host ''
        Read-Host '按 Enter 停止前端和后端'
    }
} catch {
    Write-Host "`n启动失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    foreach ($process in @($frontendProcess, $backendProcess)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
