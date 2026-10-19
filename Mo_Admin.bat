@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong ban thu. Xem docs\HUONG_DAN_ADMIN.md
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import flask, cryptography, waitress" >nul 2>&1
if errorlevel 1 (
  echo Thieu thu vien admin. Xem docs\HUONG_DAN_ADMIN.md
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m license_server --open
if errorlevel 1 pause
