$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'

function Invoke-Checked([string]$Name, [scriptblock]$Command) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Name 失败，退出码 $LASTEXITCODE" }
}

try {
    Set-Location $projectRoot
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw '未找到 .venv，请先完成首次安装。' }
    $pytestBaseTemp = Join-Path $projectRoot ('.test-runtime\pytest-' + $PID + '-' + [guid]::NewGuid().ToString('N'))
    Invoke-Checked '后端与迁移测试' { & $pythonExe -m pytest .\backend\tests -q --basetemp $pytestBaseTemp }
    Invoke-Checked 'React TypeScript 检查' { npm --prefix .\frontend run typecheck }
    Invoke-Checked 'React 生产构建' { npm --prefix .\frontend run build }
    Invoke-Checked '原业务引擎回归' { node .\test_engine.cjs }
    Invoke-Checked '原静态 UI 回归' { node .\test_ui.cjs }
    Invoke-Checked '双端启动冒烟检查' {
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_demo.ps1 -NoBrowser -SmokeTest
    }
    Write-Host "`n全部 Stage 4 验收检查通过。" -ForegroundColor Green
} catch {
    Write-Host "`n验收失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($pytestBaseTemp -and (Test-Path -LiteralPath $pytestBaseTemp)) {
        Remove-Item -LiteralPath $pytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
    Set-Location $projectRoot
}
