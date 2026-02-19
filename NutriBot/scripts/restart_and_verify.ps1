# 1. Kill any process using port 8000
# 2. Start fresh server
# 3. Run verification
# Run from project root: .\scripts\restart_and_verify.ps1

$ErrorActionPreference = "Stop"
$port = 8000

# Find PID using port 8000
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    $pids = $conn | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 }
    foreach ($procId in $pids) {
        Write-Host "Stopping process $procId on port $port..."
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

$projRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projRoot

Write-Host "Starting server on port $port..."
$cmd = "python -m uvicorn main:app --host 127.0.0.1 --port $port"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$projRoot`" && $cmd" -WindowStyle Hidden
Start-Sleep -Seconds 6

Write-Host "Running verification..."
& "$PSScriptRoot\verify_no_500.ps1" -Port $port
$result = $LASTEXITCODE

if ($result -eq 0) {
    Write-Host "Server is running at http://127.0.0.1:$port - open in browser."
}
exit $result
