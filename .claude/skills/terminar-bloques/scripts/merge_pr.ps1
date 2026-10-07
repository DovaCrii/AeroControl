# Fusiona un PR SOLO con todo en verde y `mergeStateStatus` = CLEAN, y comprueba despues que
# el commit de la rama esta de verdad en origin/main (no se confia en el mensaje de gh).
param([Parameter(Mandatory)][int]$Number)
$ErrorActionPreference = "Stop"
Set-Location (git rev-parse --show-toplevel)
$pr = gh pr view $Number -R DovaCrii/AeroControl --json state,mergeStateStatus,statusCheckRollup,headRefOid | ConvertFrom-Json
$bad = @($pr.statusCheckRollup | Where-Object { $_.conclusion -ne "SUCCESS" })
if ($pr.state -ne "OPEN" -or $pr.mergeStateStatus -ne "CLEAN" -or $bad.Count -gt 0 -or @($pr.statusCheckRollup).Count -eq 0) {
    "NO SE FUSIONA: estado=$($pr.state) merge=$($pr.mergeStateStatus) comprobaciones no verdes=$($bad.Count)"
    exit 1
}
gh pr merge $Number -R DovaCrii/AeroControl --merge --delete-branch
git fetch origin | Out-Null
git merge-base --is-ancestor $pr.headRefOid origin/main
if ($LASTEXITCODE -ne 0) { "ALERTA: el commit del PR NO esta en origin/main."; exit 1 }
$remote = (git ls-remote origin refs/heads/main).Split("`t")[0]
"OK: PR #$Number esta en origin/main. main remoto = $($remote.Substring(0, 7))"
