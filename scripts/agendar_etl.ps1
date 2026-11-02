# agendar_etl.ps1 — registra o ETL no Agendador de Tarefas do Windows.
#
# Uso:      powershell -ExecutionPolicy Bypass -File scripts\agendar_etl.ps1
# Remover:  powershell -ExecutionPolicy Bypass -File scripts\agendar_etl.ps1 -Remover
#
# As tarefas rodam na sua sessão, sem pedir senha nem privilégio de administrador.
# Com -StartWhenAvailable, um horário perdido (PC desligado) roda ao ligar o PC.
param([switch]$Remover)

$ErrorActionPreference = "Stop"
$pasta = "\FinTerminal\"

if ($Remover) {
    Get-ScheduledTask -TaskPath $pasta -ErrorAction SilentlyContinue |
        Unregister-ScheduledTask -Confirm:$false
    Write-Host "Tarefas do FinTerminal removidas."
    return
}

$raiz = Split-Path -Parent $PSScriptRoot
$python = (& py -3.11 -c "import sys; print(sys.executable)").Trim()
$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "pythonw.exe nao encontrado em $python" }

$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

function Registrar($nome, $job, $gatilhos) {
    $acao = New-ScheduledTaskAction -Execute $pythonw `
        -Argument "`"$raiz\scripts\etl_local.py`" $job" -WorkingDirectory $raiz
    Register-ScheduledTask -TaskName $nome -TaskPath $pasta -Action $acao -Trigger $gatilhos `
        -Settings $opcoes -Force | Out-Null
    Write-Host "  $nome ($job)"
}

Write-Host "Registrando tarefas em $pasta com $pythonw"
Registrar "Diario" "diario" (New-ScheduledTaskTrigger -Daily -At 07:00)
Registrar "Macro" "macro" @(
    (New-ScheduledTaskTrigger -Daily -At 12:00),
    (New-ScheduledTaskTrigger -Daily -At 18:00))
Registrar "Semanal" "semanal" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 09:00)
Registrar "MorningBrief" "brief" (New-ScheduledTaskTrigger -Weekly -At 08:00 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday)
Write-Host "Pronto. Confira no Agendador de Tarefas, pasta FinTerminal."
