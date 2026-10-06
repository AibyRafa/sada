@echo off
REM Sada - role 4 (voice identity). Double-click this file in the project folder.
REM Builds its own environment (.venv-role4) with a Python found on THIS computer
REM (role 1's .venv points to a Python on another laptop), installs what role 4 needs,
REM runs the tests and the whole role-4 pipeline. Log: reports\role4\run_log.txt
setlocal EnableExtensions
set "HERE=%~dp0"
set "VENV=%HERE%.venv-role4"
set "PY=%VENV%\Scripts\python.exe"
set "OUT=%HERE%reports\role4"
set "LOG=%OUT%\run_log.txt"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%OUT%" mkdir "%OUT%"
echo Role 4 run %date% %time% > "%LOG%"
if exist "%PY%" goto haveenv

echo [0/3] Looking for Python on this computer...
set "BASEPY="
for /d %%D in ("%APPDATA%\uv\python\cpython-3.12*") do if exist "%%D\python.exe" set "BASEPY=%%D\python.exe"
if not defined BASEPY for /d %%D in ("%APPDATA%\uv\python\cpython-3.11*") do if exist "%%D\python.exe" set "BASEPY=%%D\python.exe"
if not defined BASEPY for /f "delims=" %%P in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY for /f "delims=" %%P in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY for /f "delims=" %%P in ('py -3.10 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY if exist "C:\ProgramData\anaconda3\python.exe" set "BASEPY=C:\ProgramData\anaconda3\python.exe"
if not defined BASEPY if exist "%USERPROFILE%\anaconda3\python.exe" set "BASEPY=%USERPROFILE%\anaconda3\python.exe"
if not defined BASEPY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY goto nopython
echo Using Python: %BASEPY%
echo ===== base python: %BASEPY% ===== >> "%LOG%"
"%BASEPY%" --version >> "%LOG%" 2>&1
echo [0/3] Creating .venv-role4 - one time only...
"%BASEPY%" -m venv "%VENV%" >> "%LOG%" 2>&1
if not exist "%PY%" goto novenv

:haveenv
echo [1/3] Installing packages - first time takes several minutes, needs internet...
echo ===== install ===== >> "%LOG%"
"%PY%" -m pip install --disable-pip-version-check --upgrade pip >> "%LOG%" 2>&1
"%PY%" -c "import torch" >nul 2>nul || "%PY%" -m pip install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu >> "%LOG%" 2>&1
"%PY%" -m pip install --disable-pip-version-check -r "%HERE%requirements-role4.txt" >> "%LOG%" 2>&1
"%PY%" -m pip install --disable-pip-version-check --no-deps resemblyzer >> "%LOG%" 2>&1
echo [2/3] Running role 4 tests...
echo ===== tests ===== >> "%LOG%"
pushd "%HERE%"
"%PY%" "%HERE%tests\test_role4.py" >> "%LOG%" 2>&1
echo [3/3] Voiceprints, calibration and evaluation - a few minutes, please wait...
"%PY%" "%HERE%scripts\voice_id.py" all >> "%LOG%" 2>&1
popd
echo.
echo ================= LAST LINES OF THE LOG =================
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Encoding UTF8 -Tail 40"
echo.
echo Done. Full log: %LOG%
pause
exit /b 0

:nopython
echo No Python found on this computer. Install Python 3.12 from python.org, then run this again.
echo No Python found >> "%LOG%"
pause
exit /b 1

:novenv
echo Could not create .venv-role4 - see %LOG%
pause
exit /b 1
