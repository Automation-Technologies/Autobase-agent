@echo off
chcp 65001 >nul
echo ========================================
echo Сборка AutoBase Agent
echo ========================================
echo.

REM Проверка и создание виртуального окружения
if not exist ".venv\Scripts\activate.bat" (
    echo [1/5] Создание виртуального окружения...
    python -m venv .venv
    if errorlevel 1 (
        echo [ОШИБКА] Не удалось создать виртуальное окружение!
        echo Убедитесь, что Python установлен и доступен в PATH.
        pause
        exit /b 1
    )
    echo ✓ Виртуальное окружение создано
    echo.
) else (
    echo [1/5] Виртуальное окружение найдено
    echo.
)

echo [2/5] Активация виртуального окружения...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ОШИБКА] Не удалось активировать виртуальное окружение!
    pause
    exit /b 1
)

echo [3/5] Установка зависимостей проекта...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости!
    pause
    exit /b 1
)

echo [4/5] Установка PyInstaller...
pip install -q pyinstaller
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить PyInstaller!
    pause
    exit /b 1
)

echo [5/5] Очистка предыдущих сборок...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [6/6] Сборка исполняемого файла...
pyinstaller build.spec --clean --noconfirm

if exist "dist\AutoBaseAgent.exe" (
    echo.
    echo ========================================
    echo ✓ Сборка завершена успешно!
    echo ========================================
    echo Исполняемый файл: dist\AutoBaseAgent.exe
    echo.
    echo Создайте ярлык для запуска приложения.
    echo.
) else (
    echo.
    echo ========================================
    echo ✗ Ошибка при сборке!
    echo ========================================
    echo Проверьте логи выше для деталей.
    echo.
)

pause

