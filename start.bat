@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════╗
echo ║          AILIZA startet...           ║
echo ╚══════════════════════════════════════╝
echo.

REM Lokale IP ermitteln
for /f "tokens=*" %%i in ('python -c "import socket; s=socket.socket(); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set IP=%%i
if "%IP%"=="" set IP=127.0.0.1

echo   Auf diesem PC:    http://localhost:8000
echo   Auf dem Handy:    http://%IP%:8000
echo.
echo   Handy-Schritte:
echo   1. PC und Handy im gleichen WLAN
echo   2. Chrome auf dem Handy oeffnen
echo   3. Adresse eingeben: http://%IP%:8000
echo   4. Chrome-Menu (3 Punkte) -^> 'Zum Startbildschirm hinzufuegen'
echo.
echo   Zum Beenden: Strg+C
echo.

REM Virtuelle Umgebung aktivieren
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
  call venv\Scripts\activate.bat
)

REM Backend starten
cd apps\backend
uvicorn main:app --host 0.0.0.0 --port 8000
