@echo off
echo %* | findstr /I "username" >nul
if %ERRORLEVEL% EQU 0 (
  echo x-access-token
) else (
  echo %AQA_GIT_TOKEN%
)
