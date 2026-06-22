@echo off
title Sales Intelligence
cd /d "%~dp0"

echo ========================================
echo   Sales Intelligence
echo ========================================
echo.
echo Starting... Please wait.
echo.

set STREAMLIT=C:\Users\tailw\AppData\Roaming\Python\Python314\Scripts\streamlit.exe
set PYTHON=C:\Python314\python.exe

start /b cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8502"

if exist "%STREAMLIT%" (
    echo Streamlit: %STREAMLIT%
    "%STREAMLIT%" run app.py --server.port 8502 --browser.gatherUsageStats false
) else (
    echo Using python -m streamlit
    "%PYTHON%" -m streamlit run app.py --server.port 8502 --browser.gatherUsageStats false
)

pause