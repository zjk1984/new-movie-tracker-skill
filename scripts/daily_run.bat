@echo off
REM Daily scan + incremental PikPak download. Register via scripts\setup_windows_task.ps1
setlocal
cd /d "%~dp0.."
if not exist "data" mkdir data
echo ===== %DATE% %TIME% daily_run.bat start =====>> data\daily_run.log
set PYTHONUNBUFFERED=1
where python >nul 2>&1
if errorlevel 1 (
  echo [err] python not in PATH>> data\daily_run.log
  exit /b 1
)
python scripts\daily_run.py --headless >> data\daily_run.log 2>&1
set RC=%ERRORLEVEL%
echo ===== %DATE% %TIME% daily_run.bat exit %RC% =====>> data\daily_run.log
exit /b %RC%
