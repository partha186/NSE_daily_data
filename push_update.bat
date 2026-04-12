@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  EOD2 Evening Update — double-click or schedule via Task Scheduler
REM  Syncs NSE data, commits, and pushes to GitHub
REM ──────────────────────��──────────────────────────────────────────────────────

cd /d "%~dp0"
python push_update.py
pause
