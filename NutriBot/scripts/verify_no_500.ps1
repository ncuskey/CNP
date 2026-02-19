# Verify no 500 errors. Run from project root: .\scripts\verify_no_500.ps1
# Optionally: .\scripts\verify_no_500.ps1 -Port 8000  (test existing server)

param([int]$Port = 0)

$ErrorActionPreference = "Stop"
if ($Port -eq 0) { $Port = 9999 }

$base = "http://127.0.0.1:$Port"
$endpoints = @("/", "/today", "/dashboard", "/review", "/templates", "/templates/new", "/evidence", "/retention", "/inbox")

Write-Host "Testing port $Port..."
$failed = @()
$traceback = $null

foreach ($path in $endpoints) {
    try {
        $r = Invoke-WebRequest -Uri "$base$path" -UseBasicParsing -MaximumRedirection 5 -TimeoutSec 10
        $ok = ($r.StatusCode -eq 200) -or ($r.StatusCode -eq 302)
        if ($ok) { Write-Host "  OK  $path : $($r.StatusCode)" -ForegroundColor Green }
        else { $failed += "$path ($($r.StatusCode))"; Write-Host "  ??  $path : $($r.StatusCode)" -ForegroundColor Yellow }
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Host "  FAIL $path : $code" -ForegroundColor Red
        $failed += "$path ($code)"
        if ($code -eq 500) {
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $traceback = $reader.ReadToEnd()
                $reader.Close()
            } catch {}
        }
    }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "VERIFIED: All endpoints return 200 or 302." -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAILED: $($failed.Count) endpoint(s) - $($failed -join ', ')" -ForegroundColor Red
    if ($traceback) { Write-Host "`n500 Traceback:`n$traceback" }
    Write-Host "`nIf testing port 8000: stop any running server (Ctrl+C), then run: python -m uvicorn main:app --reload"
    exit 1
}
