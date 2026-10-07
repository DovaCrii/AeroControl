# Espera el CI de un PR hasta MaxSeconds (por omisión 540 s, bajo el tope de 10 min de una
# llamada). Código de salida: 0 todo en verde, 1 algo falló, 2 sigue en curso (volver a llamarlo).
param(
    [Parameter(Mandatory)][int]$Number,
    [int]$MaxSeconds = 540
)
$ErrorActionPreference = "Stop"
Set-Location (git rev-parse --show-toplevel)
$deadline = (Get-Date).AddSeconds($MaxSeconds)
while ($true) {
    $pr = gh pr view $Number -R DovaCrii/AeroControl --json state,mergeStateStatus,statusCheckRollup,headRefName | ConvertFrom-Json
    $checks = @($pr.statusCheckRollup)
    $running = @($checks | Where-Object { $_.status -ne "COMPLETED" })
    # Sin comprobaciones registradas todavía no es "verde": el CI aun no arranco.
    if ($checks.Count -gt 0 -and $running.Count -eq 0) { break }
    if ((Get-Date) -gt $deadline) {
        "SIGUE EN CURSO: PR #$Number ($($pr.headRefName)) - volver a llamar a wait_ci.ps1"
        exit 2
    }
    Start-Sleep -Seconds 30
}
$bad = @($checks | Where-Object { $_.conclusion -ne "SUCCESS" })
$line = ($checks | ForEach-Object { "{0}:{1}" -f $_.name, $_.conclusion }) -join ", "
"PR #{0} [{1}] merge={2}  {3}" -f $Number, $pr.state, $pr.mergeStateStatus, $line
if ($bad.Count -gt 0) { "FALLO: leer con  gh run view <id> --log-failed"; exit 1 }
exit 0
