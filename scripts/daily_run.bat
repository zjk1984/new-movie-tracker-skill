@echo off
REM Daily scan + incremental PikPak download. Register in Task Scheduler at 07:00.
cd /d "%~dp0.."
if not exist "data" mkdir data
python scripts\daily_run.py --headless >> data\daily_run.log 2>&1
