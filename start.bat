@echo off
rem ============================================================
rem  FabSim3D one-click launcher for Windows
rem  - finds Python 3 (py launcher or python on PATH)
rem  - creates a private virtual env in .venv on first run
rem  - installs / updates requirements.txt when it changes
rem  - starts the app; any arguments are passed to main.py
rem    e.g.  start.bat --lang en      start.bat --lesson 1
rem ============================================================
setlocal
cd /d "%~dp0"
title FabSim3D

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\requirements.installed"

if exist "%VPY%" goto :deps

rem ---------- locate a system Python ----------
set "PY="
rem prefer versions that panda3d ships wheels for, then any Python 3
for %%V in (3.12 3.11 3.10 3.13 3.9) do if not defined PY (py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V")
if defined PY goto :mkvenv
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :mkvenv
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :mkvenv

echo.
echo [FabSim3D] Python 3.8+ was not found.
echo            Please install Python 3 (64-bit) from https://www.python.org/downloads/
echo            and tick "Add python.exe to PATH" in the installer, then run start.bat again.
echo.
pause
exit /b 1

:mkvenv
echo [FabSim3D] First run: creating virtual environment in %VENV% ...
%PY% -m venv "%VENV%"
if errorlevel 1 goto :fail_venv
if not exist "%VPY%" goto :fail_venv

:deps
rem ---------- install requirements if missing or changed ----------
if not exist "%STAMP%" goto :install
fc /b "requirements.txt" "%STAMP%" >nul 2>&1
if errorlevel 1 goto :install
goto :run

:install
echo [FabSim3D] Installing dependencies (panda3d, numpy, matplotlib) ...
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip >nul 2>&1
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if not errorlevel 1 goto :installed
echo [FabSim3D] Default package index failed, retrying with Tsinghua mirror ...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :fail_pip
:installed
copy /y "requirements.txt" "%STAMP%" >nul

:run
echo [FabSim3D] Starting ...
"%VPY%" main.py %*
if errorlevel 1 goto :fail_run
exit /b 0

:fail_venv
echo.
echo [FabSim3D] Could not create the virtual environment in %VENV%.
echo            Delete the %VENV% folder and try again.
pause
exit /b 1

:fail_pip
echo.
echo [FabSim3D] Installing dependencies failed. Check your network connection and run start.bat again.
pause
exit /b 1

:fail_run
echo.
echo [FabSim3D] The program exited with an error (see messages above).
pause
exit /b 1
