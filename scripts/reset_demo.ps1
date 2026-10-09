$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'

try {
    $headers = @{
        'X-Demo-Role' = 'operations'
        'X-Demo-Actor' = 'windows-reset-script'
    }
    try {
        $result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8001/api/demo/reset' -Headers $headers -TimeoutSec 4
        Write-Host "后端在线，已通过 API 重置：$($result.orders)单 / $($result.parcels)袋 / $($result.merchants)家商户。" -ForegroundColor Green
    } catch {
        if (-not (Test-Path -LiteralPath $pythonExe)) { throw "未找到虚拟环境：$pythonExe" }
        Write-Host '后端未运行，改为直接重置本地 SQLite…' -ForegroundColor Yellow
        & $pythonExe -m backend.reset_demo
        if ($LASTEXITCODE -ne 0) { throw '本地数据库重置命令失败。' }
    }
} catch {
    Write-Host "重置失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
