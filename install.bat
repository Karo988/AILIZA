@echo off
REM AILIZA Schnell-Installation fuer Windows
SETLOCAL

SET MODE=%1
IF "%MODE%"=="" SET MODE=core

ECHO === AILIZA Installer ===
ECHO Modus: %MODE%  (Optionen: core ^| full)
ECHO.

REM Python pruefen
WHERE python >nul 2>&1
IF ERRORLEVEL 1 (
  ECHO FEHLER: Python nicht gefunden.
  ECHO Bitte installieren: https://python.org/downloads
  EXIT /B 1
)

REM Virtuelle Umgebung
IF NOT EXIST .venv (
  ECHO Erstelle virtuelle Umgebung...
  python -m venv .venv
)

CALL .venv\Scripts\activate.bat

ECHO Installiere Abhaengigkeiten (%MODE%)...
IF "%MODE%"=="full" (
  pip install --upgrade pip -q
  pip install -r apps\backend\requirements-full.txt -q
  ECHO Lade Sprachmodell...
  python -m spacy download de_core_news_sm -q
) ELSE (
  pip install --upgrade pip -q
  pip install -r apps\backend\requirements-core.txt -q
)

REM .env anlegen
IF NOT EXIST apps\backend\.env (
  ECHO AILIZA_EXTERNAL_LLM_ENABLED=false > apps\backend\.env
  ECHO GROQ_API_KEY= >> apps\backend\.env
  ECHO ANTHROPIC_API_KEY= >> apps\backend\.env
  ECHO OPENAI_API_KEY= >> apps\backend\.env
  ECHO MISTRAL_API_KEY= >> apps\backend\.env
  ECHO .env angelegt -- bitte API-Keys eintragen.
)

ECHO.
ECHO AILIZA bereit!
ECHO Starten mit:  .venv\Scripts\activate && uvicorn apps.backend.main:app --reload
IF "%MODE%"=="core" ECHO Tipp: Fuer volle KI-Features: install.bat full
ENDLOCAL
