@echo off
setlocal
cd /d "%~dp0"
if not exist .env (
 echo Copy .env.example to .env and fill DATABASE_URL and APP_SECRET first.
 pause
 exit /b 1
)
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
set COOKIE_SECURE=false
.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
pause
