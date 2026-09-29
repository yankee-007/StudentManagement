@echo off
cd /d "%~dp0"
if exist "D:\miniconda3\envs\groupmessaging\python.exe" (
    "D:\miniconda3\envs\groupmessaging\python.exe" main.py
) else (
    python main.py
)
if errorlevel 1 pause
