@echo off
rem Perler Bead Studio launcher.
rem Keep this file ASCII only. Do not add chcp 65001 here.
rem Chinese messages are printed by launcher.py instead.
setlocal enableextensions
cd /d "%~dp0"
title Perler Bead Studio

set "PY="
set "CAND="

rem 1. python from PATH, skipping the Microsoft Store stub
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo %%i | find /i "WindowsApps" >nul || set "CAND=%%i"
)
if not defined CAND goto :try_py
"%CAND%" -c "import tkinter,PIL" >nul 2>nul
if not errorlevel 1 set "PY=%CAND%"
if defined PY goto :run

:try_py
rem 2. the py launcher
where py >nul 2>nul
if errorlevel 1 goto :try_paths
py -3 -c "import tkinter,PIL" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :run

:try_paths
rem 3. common install locations
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%~dp0python\python.exe"
) do (
    if not defined PY if exist %%p (
        %%p -c "import tkinter,PIL" >nul 2>nul
        if not errorlevel 1 set "PY=%%p"
    )
)
if defined PY goto :run

rem 4. hand over to launcher.py, which has a longer candidate list.
rem    If nothing is found it prints the install instructions itself.
where py >nul 2>nul
if errorlevel 1 goto :last
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :run

:last
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :run
set "PY=python"
goto :run

:run
echo Using Python: %PY%
%PY% "%~dp0launcher.py"
set "RC=%errorlevel%"
if "%RC%"=="0" goto :done
echo.
echo The program exited with code %RC%.
pause

:done
endlocal
exit /b 0
