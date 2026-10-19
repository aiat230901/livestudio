@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Chua co moi truong ban thu. Xem docs\HUONG_DAN_BAN_THU.md
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import PySide6, cryptography" >nul 2>&1
if errorlevel 1 (
  echo Thieu thu vien giao dien hoac giay phep. Xem docs\HUONG_DAN_BAN_THU.md
  pause
  exit /b 1
)
start "Live Studio" ".venv\Scripts\pythonw.exe" -m desktop.app
