param(
    [Parameter(Mandatory)][string]$Worktree,
    [Parameter(Mandatory)][string]$Title,
    [Parameter(Mandatory)][string]$BodyFile
)
# Pone al dia una rama con origin/main (conservando ambos lados en CHANGELOG, MASTER_PLAN y .po),
# recompila el .mo, empuja y abre el PR. Si queda otro conflicto, se detiene y lo dice.
# Lo llama land_branch.ps1; no hace falta llamarlo a mano.
# OJO: la resolucion automatica conserva AMBOS lados; si dos ramas editaron la MISMA fila,
# revisar el resultado (y HANDOFF.md no se resuelve solo: un conflicto ahi detiene el script).
$ErrorActionPreference = "Stop"
Set-Location $Worktree
$branch = git branch --show-current
"rama: $branch"
git fetch origin 2>&1 | Out-Null
git merge origin/main 2>&1 | Select-Object -Last 2
$unmerged = @(git diff --name-only --diff-filter=U)
$auto = @('CHANGELOG.md', 'MASTER_PLAN.md', 'locale/es/LC_MESSAGES/django.po')
foreach ($f in $unmerged) {
    if ($auto -contains $f) {
        $t = [IO.File]::ReadAllText((Resolve-Path $f))
        $t = [regex]::Replace($t, '(?m)^(<<<<<<< [^\r\n]*|=======|>>>>>>> [^\r\n]*)\r?\n', '')
        if ($f -like '*.po') { $t = [regex]::Replace($t, '(?m)^((?:msgstr |")[^\r\n]*)(\r?\n)(?=msgid |msgctxt |#)', '$1$2$2') }
        [IO.File]::WriteAllText((Resolve-Path $f), $t, [Text.UTF8Encoding]::new($false))
        git add $f
    }
    elseif ($f -like '*.mo') { "(.mo se regenera)" }
    else { throw "CONFLICTO SIN RESOLVER AUTOMATICO: $f" }
}
if ($unmerged -contains 'locale/es/LC_MESSAGES/django.mo' -or $unmerged -contains 'locale/es/LC_MESSAGES/django.po') {
    uv run python -c "import polib;p=polib.pofile('locale/es/LC_MESSAGES/django.po');p.save_as_mofile('locale/es/LC_MESSAGES/django.mo')"
    git add locale/es/LC_MESSAGES/django.mo locale/es/LC_MESSAGES/django.po
}
if ($unmerged -contains 'locale/es/LC_MESSAGES/django.po') {
    uv run python (Join-Path $PSScriptRoot 'dedupe_po.py')
    git add locale/es/LC_MESSAGES/django.mo locale/es/LC_MESSAGES/django.po
}
if (@(git diff --name-only --diff-filter=U).Count -gt 0) { throw "quedan conflictos" }
if (git status --short | Select-String '^(M|A|D|R)') { git commit -q -m "merge: main en $branch" }
# Guardia contra reversiones silenciosas (LV-409): ningun PR borra migraciones ni pruebas de main.
$gone = @(git diff --diff-filter=D --name-only origin/main HEAD | Where-Object { $_ -match '/migrations/\d|/test[^/]*\.py$' })
if ($gone.Count -gt 0) { throw "REVERSION: el PR borraria $($gone -join ', ')" }
# Guardia contra filas fantasma: ningun PR puede borrar un LV-N que ya esta en main.
$lvRe = 'LV-\d+'
foreach ($doc in 'MASTER_PLAN.md', 'CHANGELOG.md') {
    $before = @([regex]::Matches((git show "origin/main:$doc" | Out-String), $lvRe) | ForEach-Object Value | Sort-Object -Unique)
    $after = @([regex]::Matches((Get-Content $doc -Raw), $lvRe) | ForEach-Object Value | Sort-Object -Unique)
    $lost = @($before | Where-Object { $after -notcontains $_ })
    if ($lost.Count -gt 0) { throw "FILA FANTASMA: $doc perderia $($lost -join ', ')" }
}
pwsh -NoProfile -File (Join-Path $PSScriptRoot 'open_pr.ps1') -Title $Title -BodyFile $BodyFile 2>&1 | Select-Object -Last 2
