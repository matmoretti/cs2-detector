@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"
"%PYEXE%" analisar.py %1
echo.
pause
