param(
    [Parameter(Mandatory = $true)]
    [int]$ParentPID
)

$folder = "C:\Users\Claens\Desktop\llama.ccp"

$stopFlag    = Join-Path $folder "watchdog-stop.flag"
$restartFile = Join-Path $folder "watchdog-restart.txt"
$errorLog    = Join-Path $folder "watchdog-errors.log"
$historyLog  = Join-Path $folder "watchdog-history.log"
$runtimeLog  = Join-Path $folder "viernes-runtime.log"

# =================================================
# CONFIGURACION
# =================================================

$checkIntervalSeconds = 1

$noProgressSeconds = 30

$maxGenerationSeconds = 120

$highGpuLimit = 80
$highGpuSeconds = 120

# =================================================
# LOGS
# =================================================

$runtimeTailLines = 300

# Comprobaciones costosas separadas del latido de 1 s
$processCheckIntervalSeconds = 2
$gpuCheckIntervalSeconds = 5
$historyMaxLines = 500

# =================================================
# ESTADO
# =================================================

$script:lastRuntimeLength = -1
$script:lastProcessCheck = [datetime]::MinValue
$script:lastGpuCheck = [datetime]::MinValue
$script:cachedViernes = $null

$script:lastTokenLine = ""
$script:lastTokenTime = $null

$script:generationStartTime = $null
$script:generationTask = $null

$script:lastTokenNumber = 0

$script:highGpuCounter = 0

# -------------------------------------------------
# CONTROL DE ERROR DE CONTEXTO
#
# Evita detectar varias veces el mismo error
# durante la carrera entre watchdog y launcher.
# -------------------------------------------------

$script:lastContextError = ""

# -------------------------------------------------
# HISTORIAL DE REINICIOS
#
# Se conserva solo como diagnostico.
# Ya no existe limite de reinicios ni modo revision.
# -------------------------------------------------

$script:restartHistory = @()

# =================================================
# LOG OPERATIVO
# =================================================

function Write-Log {

    param(
        [string]$Message
    )

    try {

        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        Add-Content `
            -Path $errorLog `
            -Value "[$timestamp] $Message" `
            -Encoding UTF8
    }
    catch {
    }
}

# =================================================
# HISTORIAL DE INCIDENTES
# =================================================

function Write-History {

    param(
        [string]$Reason,
        [string]$Task = "",
        [string]$ProcessID = ""
    )

    try {

        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

        Add-Content `
            -Path $historyLog `
            -Value "[$timestamp] REINICIO" `
            -Encoding UTF8

        Add-Content `
            -Path $historyLog `
            -Value "Motivo: $Reason" `
            -Encoding UTF8

        if ($Task -ne "") {

            Add-Content `
                -Path $historyLog `
                -Value "Task: $Task" `
                -Encoding UTF8
        }

        if ($ProcessID -ne "") {

            Add-Content `
                -Path $historyLog `
                -Value "PID llama-server: $ProcessID" `
                -Encoding UTF8
        }

        Add-Content `
            -Path $historyLog `
            -Value "PID padre: $ParentPID" `
            -Encoding UTF8

        Add-Content `
            -Path $historyLog `
            -Value "-----------------------------------------" `
            -Encoding UTF8

        if (Test-Path $historyLog) {

            $history = @(
                Get-Content `
                    -Path $historyLog `
                    -ErrorAction SilentlyContinue
            )

            if ($history.Count -gt $historyMaxLines) {

                $history |
                    Select-Object -Last $historyMaxLines |
                    Set-Content `
                        -Path $historyLog `
                        -Encoding UTF8
            }
        }
    }
    catch {
    }
}

# =================================================
# PADRE
# =================================================

function Test-ParentAlive {

    try {

        Get-Process `
            -Id $ParentPID `
            -ErrorAction Stop |
            Out-Null

        return $true
    }
    catch {

        return $false
    }
}

# =================================================
# VIERNES
# =================================================

function Get-ViernesProcess {

    try {

        $processes = Get-CimInstance `
            Win32_Process `
            -Filter "Name = 'llama-server.exe'" `
            -ErrorAction Stop

        foreach ($process in $processes) {

            if ([int]$process.ParentProcessId -eq $ParentPID) {

                return Get-Process `
                    -Id $process.ProcessId `
                    -ErrorAction SilentlyContinue
            }
        }

        return $null
    }
    catch {

        return $null
    }
}

# =================================================
# GPU CUDA
# =================================================

function Get-GpuUsage {

    try {

        $gpu = Get-Counter `
            "\GPU Engine(*)\Utilization Percentage" `
            -ErrorAction Stop

        $values = @(
            $gpu.CounterSamples |
                Where-Object {
                    $_.InstanceName -match "engtype_CUDA"
                } |
                ForEach-Object {
                    [double]$_.CookedValue
                }
        )

        if ($values.Count -eq 0) {
            return $null
        }

        $maximum = (
            $values |
                Measure-Object -Maximum
        ).Maximum

        return [math]::Round($maximum, 1)
    }
    catch {

        return $null
    }
}

# =================================================
# LEER RUNTIME
# =================================================

function Get-RuntimeLines {

    try {

        if (-not (Test-Path $runtimeLog)) {
            return @()
        }

        return @(
            Get-Content `
                -Path $runtimeLog `
                -Tail $runtimeTailLines `
                -ErrorAction Stop
        )
    }
    catch {

        return @()
    }
}

# =================================================
# DETECTAR CONTEXTO EXCEDIDO
# =================================================

function Get-ContextError {

    param(
        [array]$Lines
    )

    for ($i = $Lines.Count - 1; $i -ge 0; $i--) {

        $line = [string]$Lines[$i]

        if (
            $line -match "exceeds the available context size" -or
            $line -match "exceeds.*context size" -or
            $line -match "running out of context capacity"
        ) {

            return $line
        }
    }

    return ""
}

# =================================================
# OBTENER TASK DEL ERROR DE CONTEXTO
# =================================================

function Get-ContextTask {

    param(
        [array]$Lines
    )

    for ($i = $Lines.Count - 1; $i -ge 0; $i--) {

        $line = [string]$Lines[$i]

        if ($line -match "task\s+(\d+)\s*\|") {

            return $matches[1]
        }

        if ($line -match "processing task,\s*id\s*=\s*(\d+)") {

            return $matches[1]
        }
    }

    return ""
}

# =================================================
# REGISTRAR REINICIO
#
# Solo mantiene informacion diagnostica.
# No existe limite de reinicios.
# =================================================

function Register-Restart {

    param(
        [string]$Task
    )

    $now = Get-Date

    $entry = [PSCustomObject]@{
        Time = $now
        Task = [string]$Task
    }

    $script:restartHistory += $entry

    return $script:restartHistory.Count
}

# =================================================
# REINICIO
# =================================================

function Request-Restart {

    param(
        [string]$Reason,
        [string]$Task = ""
    )

    Write-Host ""
    Write-Host "========================================="
    Write-Host "[WATCHDOG] REINICIO SOLICITADO"
    Write-Host "[WATCHDOG] $Reason"
    Write-Host "========================================="
    Write-Host ""

    Write-Log "REINICIO SOLICITADO: $Reason"

    $viernes = Get-ViernesProcess

    $processID = ""

    if ($null -ne $viernes) {

        $processID = [string]$viernes.Id
    }

    # ---------------------------------------------
    # REGISTRAR INCIDENTE
    # ---------------------------------------------

    Write-History `
        -Reason $Reason `
        -Task $Task `
        -ProcessID $processID

    # ---------------------------------------------
    # REGISTRAR REINICIO
    #
    # Solo diagnostico.
    # No existe maximo ni modo revision.
    # ---------------------------------------------

    $restartCount = Register-Restart -Task $Task

    if ($Task -ne "") {

        Write-Log (
            "Reinicio registrado. Task=$Task. " +
            "Reinicios registrados en esta sesion: $restartCount"
        )
    }
    else {

        Write-Log (
            "Reinicio general registrado. " +
            "Reinicios registrados en esta sesion: $restartCount"
        )
    }

    # ---------------------------------------------
    # GUARDAR MOTIVO
    # ---------------------------------------------

    try {

        Set-Content `
            -Path $restartFile `
            -Value $Reason `
            -Encoding ASCII
    }
    catch {

        Write-Log (
            "ERROR escribiendo restartFile: " +
            $_.Exception.Message
        )
    }

    # ---------------------------------------------
    # TERMINAR VIERNES
    # ---------------------------------------------

    if ($null -ne $viernes) {

        try {

            $viernes.Kill()

            Write-Host "[WATCHDOG] llama-server terminado."
            Write-Log "llama-server terminado por watchdog."
        }
        catch {

            Write-Log (
                "ERROR terminando llama-server: " +
                $_.Exception.Message
            )
        }
    }

    # ---------------------------------------------
    # RESET
    # ---------------------------------------------

    $script:lastTokenLine = ""
    $script:lastTokenTime = $null
    $script:generationStartTime = $null
    $script:generationTask = $null
    $script:lastTokenNumber = 0
    $script:highGpuCounter = 0
    $script:lastRuntimeLength = -1
    $script:lastProcessCheck = [datetime]::MinValue
    $script:lastGpuCheck = [datetime]::MinValue
    $script:cachedViernes = $null

    return $true
}

# =================================================
# INICIO
# =================================================

Write-Host ""
Write-Host "========================================="
Write-Host "       WATCHDOG V8 - VIERNES"
Write-Host "========================================="
Write-Host ""

Write-Host "[WATCHDOG] PID padre: $ParentPID"
Write-Host "[WATCHDOG] Proceso vigilado: llama-server.exe"
Write-Host "[WATCHDOG] Log: $runtimeLog"
Write-Host "[WATCHDOG] Sin progreso: $noProgressSeconds s"
Write-Host "[WATCHDOG] Generacion maxima: $maxGenerationSeconds s"
Write-Host "[WATCHDOG] GPU secundaria: > $highGpuLimit% durante $highGpuSeconds s"
Write-Host "[WATCHDOG] Reinicios: sin limite"
Write-Host "[WATCHDOG] Contexto excedido: REINICIO"
Write-Host "[WATCHDOG] Contexto detectado aunque llama-server haya muerto: SI"
Write-Host "[WATCHDOG] Runtime: solo se relee cuando cambia"
Write-Host "[WATCHDOG] GPU: cada $gpuCheckIntervalSeconds s"
Write-Host ""

Write-Log "WATCHDOG V8 INICIADO. PID padre: $ParentPID"
Write-Log "Proceso vigilado: llama-server.exe"
Write-Log "Log runtime: $runtimeLog"
Write-Log "Sin progreso: $noProgressSeconds s"
Write-Log "Generacion maxima: $maxGenerationSeconds s"
Write-Log "GPU secundaria: > $highGpuLimit% durante $highGpuSeconds s"
Write-Log "Reinicios: sin limite"
Write-Log "Contexto detectado aunque llama-server haya muerto: SI"
Write-Log "Runtime: solo se relee cuando cambia"
Write-Log "GPU: cada $gpuCheckIntervalSeconds s"

# =================================================
# BUCLE PRINCIPAL
# =================================================

while ($true) {

    Start-Sleep -Seconds $checkIntervalSeconds

    # =================================================
    # PADRE
    # =================================================

    if (-not (Test-ParentAlive)) {

        Write-Host "[WATCHDOG] Padre cerrado. Saliendo."
        Write-Log "PADRE CERRADO. Watchdog finalizado."

        $viernes = Get-ViernesProcess

        if ($null -ne $viernes) {

            try {

                $viernes.Kill()

                Write-Log (
                    "llama-server terminado porque el padre fue cerrado."
                )
            }
            catch {
            }
        }

        break
    }

    # =================================================
    # STOP FLAG
    # =================================================

    if (Test-Path $stopFlag) {

        Write-Host "[WATCHDOG] STOP FLAG detectado."
        Write-Log "STOP FLAG detectado. Watchdog finalizado."

        $viernes = Get-ViernesProcess

        if ($null -ne $viernes) {

            try {

                $viernes.Kill()

                Write-Log (
                    "llama-server terminado por STOP FLAG."
                )
            }
            catch {
            }
        }

        break
    }

    # =================================================
    # LEER RUNTIME ANTES DE COMPROBAR LLAMA-SERVER
    #
    # Esto permite detectar un error de contexto aunque
    # llama-server haya terminado inmediatamente.
    # =================================================

    $runtimeChanged = $false
    $runtimeLength = -1

    try {

        if (Test-Path $runtimeLog) {

            $runtimeLength = (Get-Item $runtimeLog).Length

            if ($runtimeLength -ne $script:lastRuntimeLength) {

                $runtimeChanged = $true
            }
        }
    }
    catch {
    }

    # Solo volvemos a leer el runtime cuando realmente ha cambiado.
    $lines = @()

    if (
        $runtimeChanged -or
        $script:lastRuntimeLength -lt 0
    ) {

        $lines = Get-RuntimeLines
    }

    # =================================================
    # CONTROL DE TAMAÑO DEL LOG
    # =================================================

    if ($runtimeChanged) {

        try {

            if (
                $script:lastRuntimeLength -gt 0 -and
                $runtimeLength -lt $script:lastRuntimeLength
            ) {

                Write-Log "Runtime log reiniciado/truncado."

                $script:lastTokenLine = ""
                $script:lastTokenTime = $null
                $script:generationStartTime = $null
                $script:generationTask = $null
                $script:lastTokenNumber = 0
                $script:highGpuCounter = 0
                $script:lastContextError = ""
            }

            $script:lastRuntimeLength = $runtimeLength
        }
        catch {
        }
    }

    # =================================================
    # DETECTAR CONTEXTO EXCEDIDO
    #
    # Se hace antes de buscar el proceso.
    # =================================================

    if ($lines.Count -gt 0) {

        $contextError = Get-ContextError -Lines $lines

        if (
            $contextError -ne "" -and
            $contextError -ne $script:lastContextError
        ) {

            $script:lastContextError = $contextError

            $contextTask = Get-ContextTask -Lines $lines

            Write-Host ""
            Write-Host "========================================="
            Write-Host "[WATCHDOG] CONTEXTO EXCEDIDO DETECTADO"
            Write-Host "========================================="
            Write-Host "[WATCHDOG] $contextError"

            if ($contextTask -ne "") {

                Write-Host "[WATCHDOG] Task: $contextTask"
            }

            Write-Host ""

            Write-Log (
                "LIMITACION DE CONTEXTO DETECTADA. " +
                "llama-server puede haber terminado antes de ser encontrado. " +
                "Task=$contextTask"
            )

            $contextReason = (
                "llama.cpp indica exceso de contexto."
            )

            $ok = Request-Restart `
                -Reason $contextReason `
                -Task $contextTask

            if (-not $ok) {
                break
            }

            continue
        }
    }

    # =================================================
    # BUSCAR VIERNES
    # =================================================

    $now = Get-Date

    # Buscar el proceso es más caro que el latido principal.
    # Se mantiene cacheado entre comprobaciones.

    if (
        ($now - $script:lastProcessCheck).TotalSeconds -ge
        $processCheckIntervalSeconds
    ) {

        $script:cachedViernes = Get-ViernesProcess
        $script:lastProcessCheck = $now
    }

    $viernes = $script:cachedViernes

    if ($null -eq $viernes) {

        Write-Host "[WATCHDOG] llama-server no encontrado."

        $script:lastTokenLine = ""
        $script:lastTokenTime = $null
        $script:generationStartTime = $null
        $script:generationTask = $null
        $script:lastTokenNumber = 0
        $script:highGpuCounter = 0

        continue
    }

    # =================================================
    # SI NO HAY LOG
    # =================================================

    if ($lines.Count -eq 0) {

        Write-Host "[WATCHDOG] Runtime log: esperando datos."

        continue
    }

    # =================================================
    # BUSCAR ULTIMO TOKEN
    # =================================================

    $latestTokenLine = $null
    $latestTokenNumber = $null
    $latestTask = $null
    $latestTokenIndex = -1

    for ($i = $lines.Count - 1; $i -ge 0; $i--) {

        $line = [string]$lines[$i]

        if (
            $line -match "slot\s+process_toke[n]?:\s*id\s+\d+\s*\|\s*task\s+(\d+)\s*\|\s*n_gen\s*=\s*(\d+)"
        ) {

            $latestTask = [int]$matches[1]

            $latestTokenNumber = [int]$matches[2]

            $latestTokenLine = $line

            $latestTokenIndex = $i

            break
        }
    }

    # =================================================
    # BUSCAR ULTIMO FIN
    # =================================================

    $latestFinishLine = $null
    $latestFinishIndex = -1

    if ($latestTokenIndex -ge 0) {

        for (
            $i = $lines.Count - 1;
            $i -gt $latestTokenIndex;
            $i--
        ) {

            $line = [string]$lines[$i]

            if (
                $line -match "finish_reason" -or
                $line -match "stop processing: n_tokens" -or
                $line -match "stopped by EOS" -or
                $line -match "stop_type.*eos"
            ) {

                $latestFinishLine = $line

                $latestFinishIndex = $i

                break
            }
        }
    }

    # =================================================
    # DETECTAR NUEVA GENERACION
    # =================================================

    if ($null -ne $latestTokenLine) {

        if ($latestTokenLine -ne $script:lastTokenLine) {

            $script:lastTokenLine = $latestTokenLine

            $script:lastTokenTime = Get-Date

            if (
                $null -eq $script:generationTask -or
                $script:generationTask -ne $latestTask -or
                $latestTokenNumber -lt $script:lastTokenNumber
            ) {

                $script:generationTask = $latestTask

                $script:generationStartTime = Get-Date

                Write-Log (
                    "GENERACION INICIADA. task={0} n_gen={1}" -f
                    $latestTask,
                    $latestTokenNumber
                )
            }

            $script:lastTokenNumber = $latestTokenNumber

            Write-Host (
                "[WATCHDOG] Generando | task: {0} | token: {1}" -f
                $latestTask,
                $latestTokenNumber
            )
        }
    }

    # =================================================
    # GENERACION ACTIVA
    # =================================================

    $generationActive = (
        $null -ne $script:generationStartTime -and
        $null -ne $script:lastTokenTime
    )

    # =================================================
    # FINAL DE GENERACION
    # =================================================

    if (
        $generationActive -and
        $null -ne $latestFinishLine
    ) {

        $secondsSinceToken = (
            (Get-Date) - $script:lastTokenTime
        ).TotalSeconds

        if ($secondsSinceToken -ge 2) {

            $finishReason = "desconocido"
            $stopType = "desconocido"
            $truncated = "desconocido"

            if (
                $latestFinishLine -match
                '"finish_reason":"([^"]+)"'
            ) {

                $finishReason = $matches[1]
            }

            if (
                $latestFinishLine -match
                '"stop_type":"([^"]+)"'
            ) {

                $stopType = $matches[1]
            }

            if (
                $latestFinishLine -match
                '"truncated":(true|false)'
            ) {

                $truncated = $matches[1]
            }

            Write-Log (
                "GENERACION FINALIZADA. finish_reason={0} " +
                "stop_type={1} truncated={2}" -f
                $finishReason,
                $stopType,
                $truncated
            )

            # -----------------------------------------
            # CONTEXTO AGOTADO DURANTE GENERACION
            # -----------------------------------------

            if ($truncated -eq "true") {

                $contextReason = (
                    "llama.cpp indica truncated=true: " +
                    "posible agotamiento de contexto."
                )

                $ok = Request-Restart `
                    -Reason $contextReason `
                    -Task $script:generationTask

                if (-not $ok) {
                    break
                }

                continue
            }

            # -----------------------------------------
            # FINAL NORMAL
            # -----------------------------------------

            $script:generationStartTime = $null
            $script:generationTask = $null
            $script:lastTokenTime = $null
            $script:lastTokenNumber = 0
        }
    }

    # =================================================
    # GENERACION DEMASIADO LARGA
    # =================================================

    if ($generationActive) {

        $generationSeconds = (
            (Get-Date) - $script:generationStartTime
        ).TotalSeconds

        if (
            $generationSeconds -ge
            $maxGenerationSeconds
        ) {

            $longReason = (
                "Generacion activa durante " +
                "$([math]::Round($generationSeconds,1)) s. " +
                "Superado limite de " +
                "$maxGenerationSeconds s."
            )

            $ok = Request-Restart `
                -Reason $longReason `
                -Task $script:generationTask

            if (-not $ok) {
                break
            }

            continue
        }

        # =================================================
        # SIN PROGRESO
        # =================================================

        $noProgress = (
            (Get-Date) - $script:lastTokenTime
        ).TotalSeconds

        if ($noProgress -ge $noProgressSeconds) {

            $freezeReason = (
                "Generacion detectada pero sin nuevos tokens " +
                "durante $([math]::Round($noProgress,1)) s."
            )

            $ok = Request-Restart `
                -Reason $freezeReason `
                -Task $script:generationTask

            if (-not $ok) {
                break
            }

            continue
        }

        Write-Host (
            "[WATCHDOG] Activo | Generacion: {0}s | " +
            "Sin progreso: {1}s" -f
            [math]::Round($generationSeconds, 1),
            [math]::Round($noProgress, 1)
        )
    }
    else {

        Write-Host "[WATCHDOG] VIERNES EN ESPERA."

        $script:highGpuCounter = 0
    }

    # =================================================
    # GPU
    # =================================================

    if (
        $generationActive -and
        (($now - $script:lastGpuCheck).TotalSeconds -ge
        $gpuCheckIntervalSeconds)
    ) {

        $gpuUsage = Get-GpuUsage
        $script:lastGpuCheck = $now

        if ($null -ne $gpuUsage) {

            if ($gpuUsage -gt $highGpuLimit) {

                $script:highGpuCounter++
            }
            else {

                $script:highGpuCounter = 0
            }

            Write-Host (
                "[WATCHDOG] GPU CUDA: {0}% | GPU alta: {1}/{2}" -f
                $gpuUsage,
                $script:highGpuCounter,
                $highGpuSeconds
            )

            $noProgress = (
                (Get-Date) - $script:lastTokenTime
            ).TotalSeconds

            if (
                $script:highGpuCounter -ge $highGpuSeconds -and
                $noProgress -ge $noProgressSeconds
            ) {

                $gpuReason = (
                    "GPU > $highGpuLimit% durante " +
                    "$highGpuSeconds s y sin progreso de tokens."
                )

                $ok = Request-Restart `
                    -Reason $gpuReason `
                    -Task $script:generationTask

                if (-not $ok) {
                    break
                }

                continue
            }
        }
    }
}
