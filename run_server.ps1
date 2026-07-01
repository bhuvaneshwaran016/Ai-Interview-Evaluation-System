# PowerShell script to run the development server
# This avoids the Windows resource exhaustion error with uvicorn's file watcher

Set-Location "d:\sem-II project"
Write-Host "Starting Interview App Server..." -ForegroundColor Green
Write-Host ""

# Activate virtual environment
& ".\venv\Scripts\Activate.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Failed to activate virtual environment" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[OK] Virtual environment activated" -ForegroundColor Green
Write-Host ""
Write-Host "Starting server on http://127.0.0.1:8001" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop"
Write-Host ""

$env:PYTHONIOENCODING="utf-8"
python lightweight_start.py
