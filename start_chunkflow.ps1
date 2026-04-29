$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Users\wanghui\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Port = 8900

$env:CHUNKFLOW_PARSER_PRIORITY = "docling,mineru,pypdf"

Write-Host "Stopping existing ChunkFlow service on port $Port ..."
$listeners = netstat -ano | Select-String ":$Port\s+.*LISTENING"
foreach ($listener in $listeners) {
    $parts = ($listener.Line -split "\s+") | Where-Object { $_ }
    $pidText = $parts[-1]
    if ($pidText -match "^\d+$") {
        $pidValue = [int]$pidText
        try {
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            Write-Host "Stopped process $pidValue"
        } catch {
            Write-Warning "Failed to stop process ${pidValue}: $($_.Exception.Message)"
        }
    }
}

Set-Location $ProjectRoot
Write-Host "Starting ChunkFlow on http://127.0.0.1:$Port ..."
& $PythonExe -m uvicorn chunkflow.app:app --host 0.0.0.0 --port $Port
