@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"

if defined PYTHON (
  set "PYTHON_CMD=%PYTHON%"
  goto python_ready
)

where py >nul 2>nul
if errorlevel 1 goto try_python
py -3.14 -c "import sys" >nul 2>nul
if not errorlevel 1 goto use_py314
py -3.13 -c "import sys" >nul 2>nul
if not errorlevel 1 goto use_py313
py -3.12 -c "import sys" >nul 2>nul
if not errorlevel 1 goto use_py312
goto try_python

:use_py314
set "PYTHON_CMD=py -3.14"
goto python_ready

:use_py313
set "PYTHON_CMD=py -3.13"
goto python_ready

:use_py312
set "PYTHON_CMD=py -3.12"
goto python_ready

:try_python
where python >nul 2>nul
if errorlevel 1 (
  echo AQA AI Workflows Public Edition needs Python 3.12-3.14. 1>&2
  echo Install Python from https://www.python.org/downloads/ and run this file again. 1>&2
  exit /b 1
)
set "PYTHON_CMD=python"

:python_ready

%PYTHON_CMD% "%ROOT%scripts\bootstrap.py" "%ROOT%"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

for /f "usebackq delims=" %%P in (`%PYTHON_CMD% "%ROOT%scripts\bootstrap.py" "%ROOT%" --print-python`) do set "VENV_PYTHON=%%P"
set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
"%VENV_PYTHON%" -m aqa_ai_workflows_pe.cli serve %*
endlocal
