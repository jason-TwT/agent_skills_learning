@echo off
set MANAGER_PID=

REM 启动管理器（负责拉起/重启服务）
for /f "delims=" %%p in ('powershell -NoProfile -Command "$listener = $false; try { $tcp = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Parse('127.0.0.1'), 8010); $tcp.Start(); $tcp.Stop(); $listener = $true } catch { $listener = $false }; if ($listener) { $p = Start-Process -FilePath python -ArgumentList ''backend/scripts/manager.py'' -PassThru; $p.Id }"') do set MANAGER_PID=%%p

REM 等待服务启动（最多 10 秒）
powershell -NoProfile -Command ^
  "$deadline = (Get-Date).AddSeconds(10); " ^
  "while ((Get-Date) -lt $deadline) { " ^
  "  try { $tcp = New-Object Net.Sockets.TcpClient('127.0.0.1', 8000); $tcp.Close(); break } catch { Start-Sleep -Milliseconds 200 } " ^
  "}"

REM 用默认浏览器打开
start http://localhost:8000

REM 防止窗口立刻关闭
pause >nul

REM 脚本结束时关闭管理器与服务
if not "%MANAGER_PID%"=="" (
  taskkill /PID %MANAGER_PID% /T /F >nul 2>&1
)
powershell -NoProfile -Command ^
  "$p = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; " ^
  "if ($p) { $p | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force } }"
