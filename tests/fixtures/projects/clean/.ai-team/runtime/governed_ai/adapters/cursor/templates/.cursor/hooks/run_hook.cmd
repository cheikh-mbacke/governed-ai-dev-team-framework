:; if command -v python3 >/dev/null 2>&1; then exec python3 "$@"; fi; if command -v python >/dev/null 2>&1; then exec python "$@"; fi; echo "Governed AI Team: Python 3 not found (tried python3, python)." >&2; exit 127
@echo off
where python3 >nul 2>nul
if not errorlevel 1 goto run_python3
where python >nul 2>nul
if not errorlevel 1 goto run_python
where py >nul 2>nul
if not errorlevel 1 goto run_py
>&2 echo Governed AI Team: Python 3 not found ^(tried python3, python, py -3^).
exit /b 127

:run_python3
python3 %*
exit /b %errorlevel%

:run_python
python %*
exit /b %errorlevel%

:run_py
py -3 %*
exit /b %errorlevel%
