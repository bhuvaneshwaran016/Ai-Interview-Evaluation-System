@echo off
REM Run the FastAPI development server without auto-reload
REM This avoids Windows resource exhaustion errors

cd /d "d:\sem-II project"
echo Starting Interview App Server...
echo.

call venv\Scripts\activate.bat

if errorlevel 1 (
    echo Error: Failed to activate virtual environment
    pause
    exit /b 1
)

echo [OK] Virtual environment activated
echo.
echo Starting server on http://127.0.0.1:8001
echo Press Ctrl+C to stop
echo.

set PYTHONIOENCODING=utf-8
python lightweight_start.py

pause
