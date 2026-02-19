# Verify 500 is fixed: start server, hit endpoints, report pass/fail.
# Run from project root: .\scripts\verify_500_fixed.ps1

$ErrorActionPreference = "Stop"
$port = 9999
$base = "http://127.0.0.1:$port"

Write-Host "Starting server on port $port..."
$proc = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", $port -PassThru -NoNewWindow
Start-Sleep -Seconds 6

$endpoints = @(
    @{ path = "/"; expect = @(200, 302) },
    @{ path = "/today"; expect = @(200) },
    @{ path = "/dashboard"; expect = @(200) },
    @{ path = "/review"; expect = @(200) },
    @{ path = "/templates"; expect = @(200) }
)

$failed = @()
$traceback = $null

foreach ($ep in $endpoints) {
    $path = $ep.path
    $expect = $ep.expect
    try {
        $r = Invoke-WebRequest -Uri "$base$path" -UseBasicParsing -MaximumRedirection 5 -TimeoutSec 10
        if ($expect -notcontains $r.StatusCode) {
            $failed += "$path : unexpected $($r.StatusCode) (expected $($expect -join ','))"
        } else {
            Write-Host "PASS $path : $($r.StatusCode)" -ForegroundColor Green
        }
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 500) {
            $stream = $_.Exception.Response.GetResponseStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $traceback = $reader.ReadToEnd()
            $reader.Close()
        }
        $failed += "$path : $code"
        Write-Host "FAIL $path : $code" -ForegroundColor Red
    }
}

Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue

if ($failed.Count -eq 0) {
    Write-Host "`nAll endpoints OK. 500 is fixed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nFailed: $($failed -join '; ')" -ForegroundColor Red
    if ($traceback) {
        Write-Host "`n--- 500 Traceback ---`n$traceback"
    }
    exit 1
}
