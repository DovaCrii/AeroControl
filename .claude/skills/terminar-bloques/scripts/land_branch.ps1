param(
    [Parameter(Mandatory)][string]$Branch,
    [Parameter(Mandatory)][string]$Title,
    [string]$Note = ''
)
# Integra una rama de punta a punta: la pone al dia con origin/main (land.ps1), abre su PR,
# espera el CI y fusiona. Se detiene al primer fallo y dice donde.
#
# Uso, desde cualquier carpeta del repo:
#   pwsh -File .claude/skills/terminar-bloques/scripts/land_branch.ps1 -Branch codex/x -Title "feat(x): ... (LV-N)" -Note "Sin migracion."
#
# Requisitos: la rama tiene que estar abierta en un worktree propio (git worktree add) y con
# todo commiteado. Si dos ramas comparten worktree, crear uno: git worktree add .claude/worktrees/land-x codex/x
$scripts = $PSScriptRoot
$repo = (git -C $scripts rev-parse --path-format=absolute --git-common-dir) -replace '[\\/]\.git$', ''
Set-Location $repo
$wt = git worktree list --porcelain | Select-String 'worktree (.*)' | ForEach-Object { $_.Matches[0].Groups[1].Value } | Where-Object { (git -C $_ branch --show-current) -eq $Branch } | Select-Object -First 1
"worktree: $wt"
if (-not $wt) { "DETENIDO: no hallo el worktree de $Branch"; "FIN"; exit 1 }
Set-Location $wt
git fetch origin 2>&1 | Out-Null
$body = Join-Path ([IO.Path]::GetTempPath()) ('pr_body_' + ($Branch -replace '/', '_') + '.md')
$log = git log origin/main..HEAD --format='- %s%n%n%b'
Set-Content -Path $body -Value ("# $Title`n`n" + ($log -join "`n") + "`n`n$Note") -Encoding utf8
pwsh -NoProfile -File (Join-Path $scripts 'land.ps1') -Worktree $wt -Title $Title -BodyFile $body 2>&1 | Select-Object -Last 4
Set-Location $wt
$n = [int](gh pr list --head $Branch --state open --json number --jq '.[0].number')
if (-not $n) { "DETENIDO: no hay PR abierto para $Branch"; "FIN"; exit 1 }
"PR $n"
Start-Sleep 25
$r = ''
for ($i = 0; $i -lt 6 -and $r -notmatch 'SUCCESS|FALLO'; $i++) {
    $r = pwsh -NoProfile -File (Join-Path $scripts 'wait_ci.ps1') -Number $n 2>&1 | Select-Object -Last 1
}
"$n -> $r"
if ($r -notmatch 'SUCCESS') { "DETENIDO en #$n (leer: gh pr checks $n; gh run view <id> --log-failed)"; "FIN"; exit 1 }
Start-Sleep 20
pwsh -NoProfile -File (Join-Path $scripts 'merge_pr.ps1') -Number $n 2>&1 | Select-Object -Last 2
"FIN"
