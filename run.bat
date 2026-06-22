@echo off
REM Double-click to launch the Aviation Maintenance Records Processor.
REM Opens in its own app window (Edge/Chrome "app mode") rather than a browser
REM tab. Uses the bundled portable Python if present (built by
REM build_portable.bat), otherwise a system Python. Runs locally, no-LLM mode.
cd /d "%~dp0"
set "DISABLE_LLM=1"

REM Enable the Go handwriting OCR engine when it's bundled alongside the app.
if exist "%~dp0handwriting.exe" (
  set "HANDWRITING_OCR=1"
  set "HANDWRITING_BIN=%~dp0handwriting.exe"
)

set "PYEXE=%~dp0runtime\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo Launching the app in its own window...
echo (You can minimize this window. Close the app window to quit.)
echo.
"%PYEXE%" app_window.py
