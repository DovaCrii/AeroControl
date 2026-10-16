# Inventario de solo lectura de lo pendiente en GitHub y en el disco: PR abiertos con su estado,
# por que fallan, ramas remotas ya fusionadas y worktrees sobrantes. No cambia nada.
$ErrorActionPreference = "Stop"
Set-Location (git rev-parse --show-toplevel)
git fetch origin --prune 2>&1 | Out-Null

"== PR abiertos =="
$prs = gh pr list -R DovaCrii/AeroControl --state open --limit 50 --json number,title,headRefName,author,mergeStateStatus,updatedAt,statusCheckRollup | ConvertFrom-Json
foreach ($p in $prs) {
    $bad = @($p.statusCheckRollup | Where-Object { $_.conclusion -and $_.conclusion -ne "SUCCESS" }).Count
    $kind = if ($p.author.login -match "dependabot") { "dependabot" } else { "propio" }
    "#{0} [{1}] merge={2} checks-no-verdes={3} ({4}) {5}" -f $p.number, $kind, $p.mergeStateStatus, $bad, ([datetime]$p.updatedAt).ToString("yyyy-MM-dd"), $p.title
}

"`n== Ramas remotas ya fusionadas en main (candidatas a borrar) =="
git branch -r --merged origin/main | Where-Object { $_ -notmatch "origin/(main|HEAD)" } | ForEach-Object { $_.Trim() }

"`n== Worktrees =="
git worktree list

"`n== Worktrees con cambios sin commitear =="
foreach ($line in (git worktree list --porcelain | Select-String "^worktree ")) {
    $path = $line.Line.Substring(9)
    if (-not (Test-Path $path)) { continue }
    $dirty = @(git -C $path status --short).Count
    if ($dirty -gt 0) { "{0}: {1} archivos" -f $path, $dirty }
}
