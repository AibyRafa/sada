@echo off
REM Sada - the whole app: API server (role 3) + frontend (web/, role 2) + roles 4 and 5.
REM Double-click, wait until the browser opens, then check clips at http://127.0.0.1:8000/verify.html
REM Keep this window open while you use the app. Close it to stop the server.
setlocal EnableExtensions
set "HERE=%~dp0"
set "PY=%HERE%.venv-role4\Scripts\python.exe"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if not exist "%PY%" goto noenv
"%PY%" -c "import sys" >nul 2>nul
if errorlevel 1 goto noenv
echo [1/2] Checking the web packages - first time needs internet...
"%PY%" -c "import starlette, uvicorn, multipart" >nul 2>nul || "%PY%" -m pip install --disable-pip-version-check -r "%HERE%requirements-app.txt"
echo [2/2] Starting Sada at http://127.0.0.1:8000  - the models take about 30 seconds to load.
echo Keep this window open. Close it to stop Sada.
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep 6; Start-Process 'http://127.0.0.1:8000/verify.html'"
pushd "%HERE%"
"%PY%" -m api.server
popd
pause
exit /b 0

:noenv
echo The Python environment is missing. Run run_role5.bat once first, then run this again.
pause
exit /b 1
