@echo off
REM Double-click to launch the Aviation Maintenance Records Processor.
REM Uses the bundled portable Python if present (built by build_portable.bat),
REM otherwise falls back to a system Python. Runs locally, no-LLM mode.
cd /d "%~dp0"
set "DISABLE_LLM=1"

set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo Starting the app... a browser tab will open at http://localhost:8501
echo (Leave this window open. Close it to stop the app.)
echo.
"%PYEXE%" -m streamlit run app.py --server.address=localhost
echo.
echo The app has stopped.
pause
