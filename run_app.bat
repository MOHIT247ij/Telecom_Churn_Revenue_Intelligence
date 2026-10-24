@echo off
REM ================================================================
REM  Telecom Churn & Revenue Intelligence - one-click Streamlit app
REM  Double-click this file to start the app in your browser.
REM ================================================================
title Telecom Churn Intelligence - Streamlit
cd /d "%~dp0"
set PYTHONUTF8=1

echo.
echo  ==========================================================
echo   Telecom Churn ^& Revenue Intelligence
echo  ==========================================================
echo.

REM --- 1. Python available? -------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python or use Anaconda Prompt.
    pause
    exit /b 1
)

REM --- 2. Streamlit installed? ----------------------------------
python -c "import streamlit, altair" >nul 2>nul
if errorlevel 1 (
    echo  [SETUP] Installing required libraries - first time only...
    python -m pip install -r python\requirements.txt
    if errorlevel 1 (
        echo  [ERROR] Library install failed. Check your internet connection.
        pause
        exit /b 1
    )
)

REM --- 3. Model ready? If not, run the pipeline once -------------
if not exist "outputs\models\churn_model.pkl" (
    echo  [SETUP] Model not found - running the data + ML pipeline, 3-4 minutes...
    pushd python
    python run_pipeline.py
    popd
    if not exist "outputs\models\churn_model.pkl" (
        echo  [ERROR] Pipeline did not finish. See the messages above.
        pause
        exit /b 1
    )
)

REM --- 4. Start the app -----------------------------------------
echo.
echo  Starting app...  browser will open at http://localhost:8501
echo  Keep this window OPEN while using the app. Close it to stop.
echo.
python -m streamlit run app\streamlit_app.py
pause
