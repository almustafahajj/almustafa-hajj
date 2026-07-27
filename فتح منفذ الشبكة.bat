@echo off
chcp 65001 >nul
title Hajj Web - open network port 8000

REM Self-elevate to Administrator (firewall changes need admin)
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting administrator permission...
  powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================
echo    Allow other devices to reach the web app
echo    (opens inbound TCP port 8000 in firewall)
echo ============================================
echo.

netsh advfirewall firewall delete rule name="HajjWeb 8000" >nul 2>&1
netsh advfirewall firewall add rule name="HajjWeb 8000" dir=in action=allow protocol=TCP localport=8000
if errorlevel 1 (
  echo [ERROR] Could not add the firewall rule.
) else (
  echo.
  echo Done. Tablets/phones on the same network can now open the link.
  echo To remove later:  netsh advfirewall firewall delete rule name="HajjWeb 8000"
)
echo.
pause
