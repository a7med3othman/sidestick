@echo off
rem Run Sidestick from source. First run creates a private
rem virtual environment (.venv) and installs the dependencies into it.
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :deps

set "PY="
rem Use a Python that pygame supports (3.9-3.13); prefer the one on PATH.
for %%V in (python "py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3.9") do if not defined PY (
    %%~V -c "import sys; sys.exit(not (3, 9) <= sys.version_info[:2] <= (3, 13))" >nul 2>&1 && set "PY=%%~V"
)
if not defined PY goto :nopython

echo Setting up Sidestick (first run only)...
%PY% -m venv .venv || goto :fail

:deps
rem Reinstall dependencies only when requirements.txt changes.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
    copy /y requirements.txt ".venv\requirements.installed" >nul
)
start "" ".venv\Scripts\pythonw.exe" Sidestick.pyw %*
exit /b 0

:nopython
echo Python 3.9 to 3.13 was not found (pygame doesn't support newer versions yet).
echo.
echo  - Easiest: download Sidestick-windows.zip from the GitHub
echo    Releases page. It needs no Python.
echo  - Or install Python from https://www.python.org/downloads/
echo    (tick "Add python.exe to PATH") and run this file again.
echo.
pause
exit /b 1

:fail
echo.
echo Setup failed. See the messages above.
pause
exit /b 1
