@echo off
REM ============================================================================
REM Build a Windows setup.exe for the whole app (Streamlit UI + Go handwriting
REM engine + a private Python runtime). Run this ONCE on a Windows build machine
REM with internet. The resulting installer needs none of these on the end user's
REM PC - they just double-click the setup.exe.
REM
REM Build-machine prerequisites:
REM   * Inno Setup 6   https://jrsoftware.org/isdl.php   (provides ISCC.exe)
REM   * Go (optional)  https://go.dev/dl/   - only to build handwriting.exe here;
REM                    otherwise drop a prebuilt handwriting.exe in this folder.
REM ============================================================================
setlocal
cd /d "%~dp0"

echo.
echo [1/3] Building the private Python runtime (if missing)...
if exist "runtime\python.exe" (
  echo     runtime\ already present - skipping. Delete it to rebuild.
) else (
  call build_portable.bat || goto :fail
)

echo.
echo [2/3] Building the Go handwriting engine (handwriting.exe)...
if exist "handwriting.exe" (
  echo     handwriting.exe already present - skipping. Delete it to rebuild.
) else (
  where go >nul 2>nul
  if errorlevel 1 (
    echo     Go not found. Either install Go, or copy a prebuilt handwriting.exe
    echo     into this folder, then re-run. Continuing without it for now...
  ) else (
    set "CGO_ENABLED=0"
    REM The Go module lives under handwriting\, so build from there and write
    REM the exe back to the repo root (the installer picks it up from here).
    pushd handwriting
    go build -trimpath -ldflags "-s -w" -o ..\handwriting.exe .\cmd\handwriting || (popd & goto :fail)
    popd
    echo     built handwriting.exe
  )
)

echo.
echo [3/3] Compiling the installer with Inno Setup...
set "ISCC=ISCC.exe"
where ISCC.exe >nul 2>nul || set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
"%ISCC%" "installer\aviation_app.iss" || goto :fail

echo.
echo === Done. ===
echo The installer is in:  dist_installer\
echo Share that setup.exe - recipients double-click it to install.
echo.
if not defined CI pause
exit /b 0

:fail
echo.
echo BUILD FAILED. See the message above.
if not defined CI pause
exit /b 1
