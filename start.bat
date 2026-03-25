@echo off
cd /d "%~dp0"

echo === Проверка обновлений ===
"python_portable\python.exe" "updater.py"
if errorlevel 1 exit /b 1

start "" "python_portable\pythonw.exe" "launcher.py"
