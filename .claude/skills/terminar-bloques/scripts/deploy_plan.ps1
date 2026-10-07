# Que falta subir a p340 y los comandos JUSTOS para hacerlo.
#   pwsh .claude/skills/terminar-bloques/scripts/deploy_plan.ps1 -From <hash que dice la VM>
# Compara lo que corre la VM con origin/main, clasifica los archivos y escribe solo los bloques
# que hacen falta: sin migraciones no hay respaldo ni migrate; sin estaticos no hay collectstatic;
# sin dependencias no hay uv sync. Un bloque por mensaje, esperando la salida de cada uno.
param(
    [Parameter(Mandatory)][string]$From,
    [string]$To = "origin/main"
)
$ErrorActionPreference = "Stop"
Set-Location (git rev-parse --show-toplevel)
git fetch origin | Out-Null
git cat-file -e "$From^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) { throw "El hash '$From' no existe aqui: pedir a la VM 'git log --oneline -1' de nuevo." }
$target = (git rev-parse --short $To).Trim()
if ((git rev-parse $From) -eq (git rev-parse $To)) { "La VM ya corre ${target}: no hay nada que subir."; exit 0 }
if ((git merge-base $From $To).Trim() -ne (git rev-parse $From).Trim()) {
    throw "La VM ($From) NO es ancestro de ${To}: no es un avance directo. Parar y revisar (rollback sin volver a main?)."
}

$files = @(git diff --name-only "$From..$To")
$hit = {
    param($pattern)
    @($files | Where-Object { $_ -match $pattern })
}
$migrations = & $hit '^apps/[^/]+/migrations/.+\.py$'
$static = & $hit '^static/'
$deps = & $hit '^(pyproject\.toml|uv\.lock)$'
$timers = & $hit '^docs/scheduled-operations\.md$'

"=== QUE FALTA SUBIR: $From -> $target ($($files.Count) archivos)"
git log --oneline "$From..$To"
""
"Lleva:  migraciones=$($migrations.Count)  estaticos=$($static.Count)  dependencias=$($deps.Count)  (el .mo va versionado: no hay compilemessages)"
$migrations | ForEach-Object { "   migracion: $_" }
if ($timers.Count -gt 0) { "   AVISO: cambio docs/scheduled-operations.md -> timers nuevos o cambiados: son del usuario (bloque mkjob)." }
""
"=== COMANDOS (un bloque por mensaje; esperar la salida de cada uno)"
""
"--- A. Estado (solo lectura). Debe decir '## main...origin/main' y el hash $((git rev-parse --short $From).Trim())"
'cd /opt/aerocontrol && git status --short --branch && git log --oneline -1'
""
$needsEnv = ($migrations.Count + $static.Count + $deps.Count) -gt 0
if ($needsEnv) {
    $backup = if ($migrations.Count -gt 0) { ' && uv run python manage.py backup && uv run python manage.py verify_backup' } else { '' }
    $why = if ($migrations.Count -gt 0) { "entorno y RESPALDO (hay migraciones; debe salir '...: restorable.')" } else { "entorno" }
    "--- B. $why"
    'set -a && source <(sudo cat /etc/aerocontrol.env) && set +a && echo "$DJANGO_SETTINGS_MODULE"' + $backup
    ""
}
$pull = 'git pull && git log --oneline -1'
if ($deps.Count -gt 0) { $pull += ' && uv sync --no-dev' }
if ($migrations.Count -gt 0) { $pull += ' && uv run python manage.py migrate --no-input' }
"--- C. Codigo" + $(if ($migrations.Count -gt 0) { " y migraciones (debe decir 'Applying ... OK' por cada una)" } else { "" })
$pull
""
$restart = 'sudo systemctl restart aerocontrol && systemctl is-active aerocontrol && git log --oneline -1'
if ($static.Count -gt 0) { $restart = 'uv run python manage.py collectstatic --no-input && ' + $restart }
"--- D. " + $(if ($static.Count -gt 0) { "Estaticos (debe copiar al menos 1) y reinicio" } else { "Reinicio" }) + ". Debe terminar en 'active' y en el hash $target"
$restart
