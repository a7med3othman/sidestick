@echo off
rem Run Controller Companion from source. First run creates a private
rem virtual environment (.venv) and installs the dependencies into it.
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :deps

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY goto :nopython

echo Setting up Controller Companion (first run only)...
%PY% -m venv .venv || goto :fail

:deps
rem Reinstall dependencies only when requirements.txt changes.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
    copy /y requirements.txt ".venv\requirements.installed" >nul
)
start "" ".venv\Scripts\pythonw.exe" ControllerCompanion.pyw %*
exit /b 0

:nopython
echo Python 3.9 or newer was not found.
echo.
echo  - Easiest: download ControllerCompanion-windows.zip from the GitHub
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
