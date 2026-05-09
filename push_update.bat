@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  nse DATA Evening Update — double-click or schedule via Task Scheduler
REM  Syncs NSE data, commits, and pushes to GitHub
REM ──────────────────────��──────────────────────────────────────────────────────

cd /d "%~dp0"
python push_update.py
pause
