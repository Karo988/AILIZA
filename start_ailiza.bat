@echo off
setlocal
cd /d "%~dp0"

REM Reihenfolge: 1) vorgegebene AILIZA_PYTHON, 2) .venv, 3) python im PATH
if defined AILIZA_PYTHON goto check_python

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

:check_python
"%AILIZA_PYTHON%" -c "import uvicorn" >nul 2>nul
if errorlevel 1 (
  echo FEHLER: In "%AILIZA_PYTHON%" ist uvicorn nicht installiert.
  echo Loesung: Vollstaendige Umgebung vorgeben, z. B. in PowerShell:
  echo   $env:AILIZA_PYTHON="C:\Pfad\zur\venv\Scripts\python.exe"
  echo oder install.bat ausfuehren.
  pause
  exit /b 1
)

"%AILIZA_PYTHON%" -m uvicorn apps.backend.main:app --host 127.0.0.1 --port 8001 --reload
pause
