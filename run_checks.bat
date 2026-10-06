@echo off
REM Sada - quick evidence run (a few minutes): all tests, end-to-end on real clips, AI-vs-baseline, time per check, self check.
REM Does NOT retrain anything. Log: reports\role5\checks_log.txt
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%HERE%.venv-role4\Scripts\python.exe"
set "LOG=%HERE%reports\role5\checks_log.txt"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%PY%" goto noenv
if not exist "%HERE%reports\role5" mkdir "%HERE%reports\role5"
echo Sada checks %date% %time% > "%LOG%"
pushd "%HERE%"
echo [1/6] Role 4 tests...
echo ===== tests role 4 ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_role4.py" >> "%LOG%" 2>&1
echo [2/6] Role 5 tests...
echo ===== tests role 5 ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_role5.py" >> "%LOG%" 2>&1
echo [3/6] End-to-end on real clips...
echo ===== end-to-end ===== >> "%LOG%"
"%PY%" "%HERE%tests\test_e2e.py" >> "%LOG%" 2>&1
echo [4/6] AI vs simpler alternatives - a few minutes...
echo ===== baselines ===== >> "%LOG%"
"%PY%" "%HERE%scripts\baselines.py" >> "%LOG%" 2>&1
echo [5/6] Time per check - about a minute...
echo ===== timing ===== >> "%LOG%"
"%PY%" "%HERE%scripts\timing.py" >> "%LOG%" 2>&1
echo [6/6] Self check...
echo ===== self check ===== >> "%LOG%"
"%PY%" "%HERE%scripts\selfcheck.py" >> "%LOG%" 2>&1
popd
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Encoding UTF8 -Tail 40"
echo.
echo Done. Full log: %LOG%
pause
exit /b 0

:noenv
echo Run run_role5.bat once first.
pause
exit /b 1
