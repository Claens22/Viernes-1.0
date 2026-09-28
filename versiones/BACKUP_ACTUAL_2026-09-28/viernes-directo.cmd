@echo off
title VIERNES - ARRANQUE COMPLETO
cd /d "C:\Users\Claens\Desktop\llama.ccp"

echo ==========================================
echo          VIERNES - ARRANQUE COMPLETO
echo ==========================================
echo.
echo [1/2] Arrancando Viernes + watchdog...
echo.

start "VIERNES" cmd /k ""C:\Users\Claens\Desktop\llama.ccp\viernes-launcher.cmd""

echo.
echo Esperando a que llama-server este disponible...
echo.

:ESPERA
powershell -NoProfile -Command "try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8081); $c.Close(); exit 0 } catch { exit 1 }"

if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto ESPERA
)

echo Viernes esta disponible.
echo.
echo [2/2] Arrancando controlador...
echo.

cd /d "C:\Users\Claens\Desktop\llama.ccp\controlador"

python controlador.py

echo.
echo ==========================================
echo      CONTROLADOR DETENIDO
echo ==========================================
pause
