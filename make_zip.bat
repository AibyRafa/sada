@echo off
REM Sada - pack the whole project into Downloads\sada_project.zip to send it.
REM Leaves out the Python environments (.venv, .venv-role4) and cache: they are big and only work on this laptop.
REM On another laptop: unzip, then run run_role5.bat once (it rebuilds the environment), then run_app.bat.
setlocal
set "HERE=%~dp0"
echo Packing the project - this takes a minute...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $src=$env:HERE.TrimEnd('\'); $dst=Join-Path $env:USERPROFILE 'Downloads\sada_project.zip'; if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }; $items = Get-ChildItem -LiteralPath $src -Force | Where-Object { @('.venv','.venv-role4','cache','__pycache__') -notcontains $_.Name } | ForEach-Object { $_.FullName }; Compress-Archive -LiteralPath $items -DestinationPath $dst -CompressionLevel Optimal; $mb=[math]::Round((Get-Item -LiteralPath $dst).Length/1MB,1); Write-Host ('Done: ' + $dst + '  (' + $mb + ' MB)')"
if errorlevel 1 echo Something went wrong - take a photo of this window.
pause
