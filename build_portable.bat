@echo off
REM ============================================================================
REM Build a fully self-contained, portable Windows bundle of the app.
REM Run this ONCE on a machine that has internet (no admin rights needed).
REM It downloads an embeddable Python into .\runtime and installs the app's
REM dependencies into it. Afterwards, zip this whole folder and send it to
REM anyone - they just unzip and double-click run.bat. No Docker, no installer.
REM ============================================================================
setlocal
cd /d "%~dp0"

set "PYVER=3.11.9"
set "EMBED=python-%PYVER%-embed-amd64.zip"
set "REQ=requirements-lite.txt"
if /i "%~1"=="full" set "REQ=requirements.txt"

echo.
echo === Building portable runtime (Python %PYVER%, deps from %REQ%) ===
echo.

echo [1/5] Downloading embeddable Python...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/%PYVER%/%EMBED%' -OutFile '%EMBED%'" || goto :fail

echo [2/5] Extracting to .\runtime ...
powershell -NoProfile -Command "Expand-Archive -Force '%EMBED%' 'runtime'" || goto :fail
del "%EMBED%" 2>nul

echo [3/5] Enabling site-packages...
powershell -NoProfile -Command "(Get-Content 'runtime\python311._pth') -replace '#import site','import site' | Set-Content 'runtime\python311._pth'" || goto :fail

echo [4/5] Bootstrapping pip...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'runtime\get-pip.py'" || goto :fail
"runtime\python.exe" "runtime\get-pip.py" --no-warn-script-location || goto :fail

echo [5/5] Installing dependencies (this can take several minutes)...
"runtime\python.exe" -m pip install --no-warn-script-location -r "%REQ%" || goto :fail

echo.
echo === Done. ===
echo The portable app is ready in this folder.
echo Next: zip this whole folder and share it. The recipient double-clicks run.bat.
echo (Tip: delete the .venv and __pycache__ folders before zipping to keep it small.)
echo.
if not defined CI pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Check your internet connection and try again.
if not defined CI pause
exit /b 1
