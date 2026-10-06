@echo off
REM Sada vs public deepfake detectors (criterion: innovation). Installs `transformers` once and downloads two
REM open detectors from Hugging Face (about 1.5 GB, first time only), then runs them and Sada on the same clips.
REM Report: reports\role5\detectors.md   Log: reports\role5\detectors_log.txt   Time: 10-30 minutes.
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%HERE%.venv-role4\Scripts\python.exe"
set "LOG=%HERE%reports\role5\detectors_log.txt"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
if not exist "%PY%" goto noenv
if not exist "%HERE%reports\role5" mkdir "%HERE%reports\role5"
echo [1/2] Checking transformers - first time needs internet...
"%PY%" -c "import transformers" >nul 2>nul || "%PY%" -m pip install --disable-pip-version-check -r "%HERE%requirements-compare.txt"
echo [2/2] Running the detectors and Sada on the same clips - downloads the models the first time...
pushd "%HERE%"
"%PY%" "%HERE%scripts\detectors.py" > "%LOG%" 2>&1
popd
powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Encoding UTF8 -Tail 45"
echo.
echo Done. Report: reports\role5\detectors.md
pause
exit /b 0

:noenv
echo Run run_role5.bat once first.
pause
exit /b 1
