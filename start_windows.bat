@echo off
setlocal EnableExtensions
set "MANAGER_PID="
set "SERVER_PID="

if "%SERVER_HOST%"=="" set "SERVER_HOST=127.0.0.1"
set "LOG_DIR=backend\logs"
set "LOG_FILE=%LOG_DIR%\server.log"
set "APP_PROFILE_DIR=%APP_PROFILE_DIR%"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :ensure_manager
call :ensure_server

call :check_port 8000
if errorlevel 1 (
  echo Server did not start on port 8000.
  if exist "%LOG_FILE%" (
    echo ---- server.log ----
    powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 50"
    echo --------------------
  )
  goto :cleanup
)

set "APP_URL=http://localhost:8000"
start "" "%APP_URL%"

REM 防止窗口立刻关闭
pause >nul
goto :cleanup

:ensure_manager
call :check_port 8010
if errorlevel 1 (
  for /f "delims=" %%p in ('powershell -NoProfile -Command "Start-Process -FilePath python -ArgumentList ''backend/scripts/manager.py'' -PassThru | Select-Object -ExpandProperty Id"') do set "MANAGER_PID=%%p"
)
call :wait_port 8010 20
exit /b 0

:ensure_server
call :check_port 8000
if not errorlevel 1 exit /b 0
call :trigger_restart
call :wait_port 8000 50
if not errorlevel 1 exit /b 0
echo Server did not start on port 8000 (via manager).
echo Fallback: starting server directly...
for /f "delims=" %%p in ('powershell -NoProfile -Command "Start-Process -FilePath python -ArgumentList ''backend/scripts/server.py'',''--no-browser'' -RedirectStandardOutput ''%LOG_FILE%'' -RedirectStandardError ''%LOG_FILE%'' -PassThru | Select-Object -ExpandProperty Id"') do set "SERVER_PID=%%p"
call :wait_port 8000 50
exit /b 0

:trigger_restart
powershell -NoProfile -Command "1..3 | ForEach-Object { try { Invoke-WebRequest -Method POST -Uri 'http://127.0.0.1:8010/restart' -UseBasicParsing -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 500 } }"
exit /b 0

:wait_port
set "PORT=%~1"
set "RETRIES=%~2"
if "%RETRIES%"=="" set "RETRIES=50"
powershell -NoProfile -Command "$port=%PORT%; $retries=%RETRIES%; for ($i=0; $i -lt $retries; $i++) { try { $tcp = New-Object Net.Sockets.TcpClient('127.0.0.1', $port); $tcp.Close(); exit 0 } catch { Start-Sleep -Milliseconds 200 } }; exit 1"
exit /b %ERRORLEVEL%

:check_port
set "PORT=%~1"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
exit /b %ERRORLEVEL%

:cleanup
if not "%MANAGER_PID%"=="" (
  taskkill /PID %MANAGER_PID% /T /F >nul 2>&1
)
if not "%SERVER_PID%"=="" (
  taskkill /PID %SERVER_PID% /T /F >nul 2>&1
)
powershell -NoProfile -Command ^
  "$p = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; " ^
  "if ($p) { $p | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force } }"
if not "%APP_PROFILE_DIR%"=="" if exist "%APP_PROFILE_DIR%" rmdir /s /q "%APP_PROFILE_DIR%"
exit /b 0
