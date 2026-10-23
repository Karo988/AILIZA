@echo off
setlocal
cd /d "%~dp0"

REM Python-Auswahl (Reihenfolge):
REM 1. AILIZA_PYTHON, falls von aussen gesetzt
REM 2. vollstaendige Umgebung %USERPROFILE%\ailiza-q11-venv
REM 3. lokale .venv im Arbeitsverzeichnis
REM 4. python aus PATH
if defined AILIZA_PYTHON goto check_python
if exist "%USERPROFILE%\ailiza-q11-venv\Scripts\python.exe" (
  set "AILIZA_PYTHON=%USERPROFILE%\ailiza-q11-venv\Scripts\python.exe"
  goto check_python
)
if exist "%~dp0.venv\Scripts\python.exe" (
  set "AILIZA_PYTHON=%~dp0.venv\Scripts\python.exe"
  goto check_python
)
where python >nul 2>nul
if errorlevel 1 (
  echo FEHLER: Kein Python gefunden. Bitte zuerst install.bat ausfuehren.
  pause
  exit /b 1
)
set "AILIZA_PYTHON=python"

:check_python
echo Verwende Python: %AILIZA_PYTHON%
"%AILIZA_PYTHON%" -c "import uvicorn, fastapi" >nul 2>nul
if errorlevel 1 (
  echo FEHLER: In dieser Python-Umgebung fehlen uvicorn oder fastapi.
  echo Python: %AILIZA_PYTHON%
  echo Loesung: AILIZA_PYTHON auf eine vollstaendige Umgebung setzen
  echo          oder install.bat ausfuehren.
  pause
  exit /b 1
)

echo.
echo AILIZA startet: http://127.0.0.1:8001
echo Zum Beenden: Strg+C
echo.
"%AILIZA_PYTHON%" -m uvicorn apps.backend.main:app --host 127.0.0.1 --port 8001 --reload
pause
