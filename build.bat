@echo off
rem Build the standalone app: dist\Sidestick\Sidestick.exe
rem and dist\Sidestick-windows.zip (what goes on GitHub Releases).
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
rem Use a Python that pygame supports (3.9-3.13); prefer the one on PATH.
for %%V in (python "py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3.9") do if not defined PY (
    %%~V -c "import sys; sys.exit(not (3, 9) <= sys.version_info[:2] <= (3, 13))" >nul 2>&1 && set "PY=%%~V"
)
if not defined PY (
    echo Python 3.9 to 3.13 is required to build; pygame doesn't support newer versions yet.
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
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\Sidestick\*' -DestinationPath 'dist\Sidestick-windows.zip'" || exit /b 1

echo.
echo Done:
echo   dist\Sidestick\Sidestick.exe
echo   dist\Sidestick-windows.zip
