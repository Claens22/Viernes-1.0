@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "C:\Users\Claens\Desktop\llama.ccp"

set "PARENT_PID="

echo.
echo =========================================
echo              VIERNES
echo =========================================
echo.
echo [VIERNES] Supervisor iniciado.
echo.

REM -------------------------------------------------
REM OBTENER PID DEL CMD SUPERVISOR
REM -------------------------------------------------

for /f "delims=" %%P in ('powershell.exe -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' -and $_.CommandLine -like '*viernes-launcher.cmd*' }; ($p | Sort-Object ProcessId | Select-Object -Last 1).ProcessId"') do (
    set "PARENT_PID=%%P"
)

echo [VIERNES] PID del CMD: %PARENT_PID%
echo.

if not defined PARENT_PID (
    echo [ERROR] No se pudo obtener el PID del CMD.
    pause
    goto END
)

REM -------------------------------------------------
REM LIMPIAR ESTADO DE SESION ANTERIOR
REM -------------------------------------------------

echo [VIERNES] Limpiando estado de la sesion anterior...

del /q "viernes-runtime.log" >nul 2>&1
del /q "watchdog-restart.txt" >nul 2>&1

echo.

REM -------------------------------------------------
REM ARRANCAR WATCHDOG OCULTO
REM -------------------------------------------------

echo [VIERNES] Arrancando watchdog...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
"Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0watchdog.ps1','-ParentPID','%PARENT_PID%'"

timeout /t 2 /nobreak >nul

echo [VIERNES] Watchdog arrancado.
echo.

REM -------------------------------------------------
REM BUCLE DE VIERNES
REM -------------------------------------------------

:LOOP

echo [VIERNES] Iniciando llama-server...
echo.

REM -------------------------------------------------
REM LLAMA-SERVER
REM
REM Controlador -> HTTP 127.0.0.1:8081
REM GPU -> CUDA0
REM
REM stdout -> pantalla
REM stderr -> viernes-runtime.log
REM -------------------------------------------------

llama-server.exe ^
    -m "Qwen3-4B-Instruct-2507-UD-Q4_K_XL.gguf" ^
    --device CUDA0 ^
    -ngl 99 ^
    --host 127.0.0.1 ^
    --port 8081 ^
    --verbose ^
    >CON 2>"viernes-runtime.log"

echo.
echo =========================================
echo [VIERNES] llama-server ha terminado.
echo =========================================
echo.

REM -------------------------------------------------
REM CIERRE NORMAL
REM -------------------------------------------------

if exist "watchdog-stop.flag" (
    echo [VIERNES] Cierre solicitado.
    del /q "watchdog-stop.flag" >nul 2>&1
    goto END
)

REM -------------------------------------------------
REM ESPERAR DECISION DEL WATCHDOG
REM -------------------------------------------------

echo [WATCHDOG] Esperando decision del watchdog...
echo.

set /a WATCHDOG_WAIT=0

:WAIT_WATCHDOG

if exist "watchdog-stop.flag" (
    echo [VIERNES] Cierre solicitado mientras se esperaba.
    del /q "watchdog-stop.flag" >nul 2>&1
    goto END
)

if exist "watchdog-restart.txt" (
    echo [WATCHDOG] Decision de reinicio recibida.
    echo.
    goto WATCHDOG_RESTART
)

timeout /t 1 /nobreak >nul

set /a WATCHDOG_WAIT+=1

if !WATCHDOG_WAIT! GEQ 15 (
    echo.
    echo [WATCHDOG] No se recibio decision en 15 segundos.
    echo [WATCHDOG] Se considera cierre inesperado.
    echo.
    goto FALLBACK_RESTART
)

goto WAIT_WATCHDOG

REM -------------------------------------------------
REM REINICIO AUTORIZADO POR WATCHDOG
REM -------------------------------------------------

:WATCHDOG_RESTART

del /q "viernes-runtime.log" >nul 2>&1

set "RESTART_REASON=Reinicio solicitado por watchdog"

if exist "watchdog-restart.txt" (
    set /p RESTART_REASON=<"watchdog-restart.txt"
    del /q "watchdog-restart.txt" >nul 2>&1
)

echo [WATCHDOG] Motivo: !RESTART_REASON!
echo [WATCHDOG] Esperando 3 segundos...
echo.

timeout /t 3 /nobreak >nul

echo [WATCHDOG] Relanzando Viernes...
echo.

goto LOOP

REM -------------------------------------------------
REM REINICIO DE EMERGENCIA
REM -------------------------------------------------

:FALLBACK_RESTART

del /q "viernes-runtime.log" >nul 2>&1

echo [WATCHDOG] Reinicio de emergencia.
echo [WATCHDOG] Motivo: El watchdog no respondio.
echo [WATCHDOG] Esperando 3 segundos...
echo.

timeout /t 3 /nobreak >nul

echo [WATCHDOG] Relanzando Viernes...
echo.

goto LOOP

REM -------------------------------------------------
REM FIN
REM -------------------------------------------------

:END

echo.
echo =========================================
echo [VIERNES] Supervisor detenido.
echo =========================================
echo.
pause