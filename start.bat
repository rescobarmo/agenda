@echo off
setlocal
title Clínica Vital - Servidor de citas
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=python
)

echo ============================================
echo  Clínica Vital - Servidor de citas
echo  URL: http://127.0.0.1:8000
echo  Presiona Ctrl+C para detener.
echo ============================================
echo.

"%PY%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo Error al iniciar el servidor. Verifica que las dependencias
    echo esten instaladas con:  pip install -r requirements.txt
    echo.
    pause
)
endlocal
