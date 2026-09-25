@echo off
rem Build the standalone app: dist\Sidestick\Sidestick.exe
rem and dist\Sidestick-windows.zip (what goes on GitHub Releases).
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
    echo Python 3.9 or newer is required to build.
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    %PY% -m venv .venv-build || exit /b 1
)
set "VPY=.venv-build\Scripts\python.exe"

echo [1/4] Installing build dependencies...
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements-dev.txt || exit /b 1

echo [2/4] Running tests...
"%VPY%" -m pytest -q || exit /b 1

echo [3/4] Building...
if not exist assets mkdir assets
"%VPY%" -m sidestick.icon assets\icon.ico || exit /b 1
"%VPY%" -m PyInstaller --noconfirm --clean --log-level WARN Sidestick.spec || exit /b 1

echo [4/4] Zipping...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\Sidestick' -DestinationPath 'dist\Sidestick-windows.zip'" || exit /b 1

echo.
echo Done:
echo   dist\Sidestick\Sidestick.exe
echo   dist\Sidestick-windows.zip
