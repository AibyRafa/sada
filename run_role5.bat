@echo off
REM Sada - role 5 (forgery and manipulation). Double-click this file in the project folder.
REM Uses the same environment as role 4 (.venv-role4). If that environment was copied from
REM another laptop it does not work here, so it is rebuilt with a Python found on THIS computer.
REM Then: installs what role 5 needs, runs the tests and the whole role-5 pipeline.
REM Log: reports\role5\run_log.txt
setlocal EnableExtensions
set "HERE=%~dp0"
set "VENV=%HERE%.venv-role4"
set "PY=%VENV%\Scripts\python.exe"
set "OUT=%HERE%reports\role5"
set "LOG=%OUT%\run_log.txt"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%OUT%" mkdir "%OUT%"
echo Role 5 run %date% %time% > "%LOG%"
if not exist "%PY%" goto findpython
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto findpython
goto haveenv

:findpython
echo [0/4] Looking for Python on this computer...
set "BASEPY="
for /d %%D in ("%APPDATA%\uv\python\cpython-3.12*") do if exist "%%D\python.exe" set "BASEPY=%%D\python.exe"
if not defined BASEPY for /d %%D in ("%APPDATA%\uv\python\cpython-3.11*") do if exist "%%D\python.exe" set "BASEPY=%%D\python.exe"
if not defined BASEPY for /f "delims=" %%P in ('py -3.12 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY for /f "delims=" %%P in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY for /f "delims=" %%P in ('py -3.13 -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY if exist "C:\ProgramData\anaconda3\python.exe" set "BASEPY=C:\ProgramData\anaconda3\python.exe"
if not defined BASEPY if exist "%USERPROFILE%\anaconda3\python.exe" set "BASEPY=%USERPROFILE%\anaconda3\python.exe"
if not defined BASEPY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "BASEPY=%%P"
if not defined BASEPY goto nopython
echo Using Python: %BASEPY%
echo ===== base python: %BASEPY% ===== >> "%LOG%"
"%BASEPY%" --version >> "%LOG%" 2>&1
echo [0/4] Creating .venv-role4 for this computer - one time only...
"%BASEPY%" -m venv --clear "%VENV%" >> "%LOG%" 2>&1
if not exist "%PY%" goto novenv
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto novenv

:haveenv
echo [1/4] Installing packages - first time takes several minutes, needs internet...
echo ===== install ===== >> "%LOG%"
"%PY%" -m pip install --disable-pip-version-check --upgrade pip >> "%LOG%" 2>&1
"%PY%" -c "import torch" >nul 2>nul || "%PY%" -m pip install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cpu >> "%LOG%" 2>&1
"%PY%" -m pip install --disable-pip-version-check -r "%HERE%requirements-role4.txt" -r "%HERE%requirements-role5.txt" >> "%LOG%" 2>&1
"%PY%" -c "import resemblyzer" >nul 2>nul || "%PY%" -m pip install --disable-pip-version-check --no-deps resemblyzer >> "%LOG%" 2>&1
pushd "%HERE%"
echo [2/4] Running tests...
echo ===== tests role 4 ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_role4.py" >> "%LOG%" 2>&1
echo ===== tests role 5 ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_role5.py" >> "%LOG%" 2>&1
echo [3/4] Role 5 pipeline: library, calibration, evaluation, models - about 15-30 minutes, please wait...
"%PY%" "%HERE%scripts\forensics.py" all >> "%LOG%" 2>&1
echo ===== baselines: AI vs simpler alternatives ===== >> "%LOG%"
"%PY%" "%HERE%scripts\baselines.py" >> "%LOG%" 2>&1
echo ===== end-to-end tests on real clips ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_e2e.py" >> "%LOG%" 2>&1
echo ===== self check ===== >> "%LOG%"
"%PY%" "%HERE%scripts\selfcheck.py" >> "%LOG%" 2>&1
echo [4/4] Two example checks...
echo ===== example: spliced clip attributed to ibn_baz ===== >> "%LOG%"
"%PY%" "%HERE%scripts\forensics.py" check "%HERE%data\spliced\speakerX_spliced_12.wav" --sheikh ibn_baz >> "%LOG%" 2>&1
echo ===== example: real clip of ibn_baz ===== >> "%LOG%"
"%PY%" "%HERE%scripts\forensics.py" check "%HERE%data\real\speakerA_real_70.wav" --sheikh ibn_baz >> "%LOG%" 2>&1
popd
echo.
echo ================= LAST LINES OF THE LOG =================
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Encoding UTF8 -Tail 45"
echo.
echo Done. Full log: %LOG%
echo Reports: %OUT%
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
