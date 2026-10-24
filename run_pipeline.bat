@echo off
REM ================================================================
REM  Re-run the full data + ML + SQL pipeline (3-4 minutes)
REM ================================================================
title Telecom Churn - Pipeline
cd /d "%~dp0python"
set PYTHONUTF8=1
python run_pipeline.py
echo.
pause
