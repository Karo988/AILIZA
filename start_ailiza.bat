@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "AILIZA_PYTHON=.venv\Scripts\python.exe"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo FEHLER: Kein Python gefunden. Bitte zuerst install.bat ausfuehren.
    pause
    exit /b 1
  )
  set "AILIZA_PYTHON=python"
)

"%AILIZA_PYTHON%" -m uvicorn apps.backend.main:app --host 127.0.0.1 --port 8001 --reload
pause
