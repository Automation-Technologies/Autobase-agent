@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"

echo === Проверка обновлений ===
"python_portable\python.exe" "updater.py"
if errorlevel 1 (
    echo [WARN] Updater завершился с ошибкой. Запуск приложения без обновления...
)

start "" "python_portable\pythonw.exe" "launcher.py"
