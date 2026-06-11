@echo off
cd /d C:\ki-liza\Ailiza
python -m uvicorn apps.backend.main:app --port 8001 --reload
pause
