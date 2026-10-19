#!/usr/bin/env bash
#
# Despliegue de AeroControl en la VM (LV-327, PR 2 de la automatizacion del despliegue).
#
# Se corre EN la VM, como el usuario del servicio, y pide la contrasena de `sudo` UNA vez:
#
#   cd /opt/aerocontrol && bash scripts/deploy.sh [--dry-run] [--status] [--backup] [--allow-noop-sync]
#
#   --dry-run          pasos 0-5 y la clasificacion: solo LEE, imprime el plan y no ejecuta nada
#   --status           solo `manage.py deploy_status` con el entorno de produccion
#   --backup           respaldo aunque no haya migraciones
#   --allow-noop-sync  no abortar si `uv sync` no instalo nada
#
# Nunca ejecuta un rollback: solo imprime el comando. Nunca lee ni guarda la contrasena
# (`sudo -v` la pide por el TTY de sudo) y nunca imprime un valor del entorno: los comandos
# de manage.py corren con `systemd-run -p EnvironmentFile=`, sin cargarlo en esta shell.
# NO instala timers (eso es del usuario, bloque mkjob).
#
# Pruebas: DEPLOY_ROOT (otra raiz), DEPLOY_ENV_FILE (otro archivo de entorno) y DEPLOY_FAKE=1
# (sin esperas) -- ver apps/core/test_deploy_script.py.

set -eEuo pipefail

ROOT="${DEPLOY_ROOT:-/opt/aerocontrol}"
ENV_FILE="${DEPLOY_ENV_FILE:-/etc/aerocontrol.env}"
HEALTH_URL="${DEPLOY_HEALTH_URL:-http://127.0.0.1:8000/health/}"
SERVICE=aerocontrol
SLEEP_UNIT=1
[[ "${DEPLOY_FAKE:-0}" == "1" ]] && SLEEP_UNIT=0

DRY=0
STATUS_ONLY=0
FORCE_BACKUP=0
ALLOW_NOOP=0
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY=1 ;;
    --status) STATUS_ONLY=1 ;;
    --backup) FORCE_BACKUP=1 ;;
    --allow-noop-sync) ALLOW_NOOP=1 ;;
    *) echo "Opcion desconocida: ${arg}" >&2; exit 2 ;;
  esac
done

STEP=0
OLD=""
NEW=""
KEEP_PID=""
PULLED=0
BACKED_UP=0
MIGRATE_STARTED=0
FAILED=0

paso() {
  STEP="$1"
  printf '\n==> %s. %s\n' "$1" "$2"
}

cleanup() {
  if [[ -n "${KEEP_PID}" ]]; then
    kill "${KEEP_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Imprime en que paso fallo y el rollback sugerido. NO lo ejecuta.
fail() {
  local reason="$1"
  [[ "${FAILED}" == "1" ]] && exit 1
  FAILED=1
  echo
  echo "=== RESUMEN"
  echo "DEPLOY FALLÓ en paso ${STEP}: ${reason}"
  if [[ "${PULLED}" == "1" && -n "${OLD}" ]]; then
    echo "Rollback sugerido (NO se ejecuta; revisar antes):"
    echo "  cd ${ROOT} && git checkout ${OLD} && sudo systemctl restart ${SERVICE}"
    if [[ "${MIGRATE_STARTED}" == "1" ]]; then
      echo "  y, como se corrio migrate, restaurar el respaldo previo:"
      echo "  manage.py restore_backup <respaldo> <destino>  (con --force solo si se decide)"
    fi
    echo "Volver a main el MISMO dia: git checkout main && git pull --ff-only"
  else
    echo "Nada del codigo cambio: no hace falta rollback."
    [[ "${BACKED_UP}" == "1" ]] && echo "(el respaldo previo quedo hecho y es inofensivo)"
  fi
  exit 1
}
trap 'fail "un comando fallo inesperadamente (linea ${LINENO})"' ERR

# manage.py como corren los timers: systemd lee el EnvironmentFile como root y baja al
# usuario del servicio; el entorno no pasa por esta shell ni por la pantalla.
SVC_USER="$(id -un)"
manage() {
  sudo systemd-run --quiet --wait --pipe --collect \
    --uid="${SVC_USER}" \
    -p WorkingDirectory="${ROOT}" \
    -p EnvironmentFile="${ENV_FILE}" \
    "${UV}" run python manage.py "$@"
}

jget() { # jget <json> <python-expr sobre d>
  printf '%s' "$1" | python3 -c "import json,sys; d=json.load(sys.stdin); print($2)"
}

health_code() {
  # En produccion Django redirige todo HTTP a HTTPS (301). El proxy delante de gunicorn manda
  # `X-Forwarded-Proto: https`; sin esa cabecera la comprobacion local recibe el 301 y falla
  # aunque la aplicacion este bien (paso 12 del primer despliegue real, 2026-10-19).
  curl -s -o /dev/null -w '%{http_code}' -H 'X-Forwarded-Proto: https' "${HEALTH_URL}" || true
}

wait_health() {
  local code=""
  for _ in 1 2 3 4 5; do
    code="$(health_code)"
    [[ "${code}" == "200" ]] && break
    sleep $((2 * SLEEP_UNIT))
  done
  printf '%s' "${code}"
}

# ---------------------------------------------------------------- 0
paso 0 "Raiz del proyecto"
cd "${ROOT}"
UV="$(command -v uv || true)"
[[ -n "${UV}" ]] || fail "uv no esta en el PATH"

if [[ "${STATUS_ONLY}" == "1" ]]; then
  paso 4 "sudo"
  sudo -v
  paso 5 "deploy_status"
  manage deploy_status
  exit 0
fi

# ---------------------------------------------------------------- 1
paso 1 "Rama y estado frente a origin"
git fetch origin
head_line="$(git status --porcelain=v1 --branch | head -n 1)"
case "${head_line}" in
  "## HEAD (no branch)"*) fail "HEAD desprendido: volver con 'git checkout main' (tras un rollback no se despliega nada)" ;;
  *"[ahead"*) fail "la VM tiene commits propios (${head_line#\#\# }): no es un avance directo" ;;
  *"[diverged"*|*"[gone"*) fail "la rama divergio o perdio su remoto (${head_line#\#\# })" ;;
  "## main...origin/main"*) echo "    ${head_line}" ;;
  *) fail "se esperaba '## main...origin/main' y hay '${head_line}'" ;;
esac

# ---------------------------------------------------------------- 2
paso 2 "Arbol limpio, sin archivos sin versionar que el pull pise"
dirty="$(git status --porcelain=v1 --branch | tail -n +2)"
if [[ -n "${dirty}" ]]; then
  NEW_TREE="$(git ls-tree -r --name-only origin/main)"
  while IFS= read -r line; do
    if [[ "${line}" == '?? '* ]]; then
      f="${line#\?\? }"
      f="${f%/}"
      if printf '%s\n' "${NEW_TREE}" | grep -qxF "${f}" || printf '%s\n' "${NEW_TREE}" | grep -q "^${f}/"; then
        fail "el archivo sin versionar '${f}' lo pisaria el pull: apartarlo antes con 'mv ${f} ~' (no rm) y comparar con diff"
      fi
    fi
  done <<<"${dirty}"
  fail "el arbol no esta limpio ($(printf '%s\n' "${dirty}" | wc -l | tr -d ' ') entradas en 'git status --short')"
fi
echo "    limpio"

# ---------------------------------------------------------------- 3
paso 3 "Que falta subir"
OLD="$(git rev-parse HEAD)"
NEW="$(git rev-parse origin/main)"
git merge-base --is-ancestor "${OLD}" "${NEW}" || fail "${OLD:0:7} no es ancestro de origin/main (${NEW:0:7}): no es un avance directo"

if [[ "${OLD}" == "${NEW}" ]]; then
  echo "    nada que subir: la VM ya corre ${NEW:0:7}"
  code="$(wait_health)"
  echo
  echo "=== RESUMEN"
  echo "DEPLOY: nada que subir (${NEW:0:7})"
  echo "health: ${code}"
  echo "HEAD == origin/main: sí"
  [[ "${code}" == "200" ]] || { STEP=12; fail "health responde '${code}' en vez de 200"; }
  exit 0
fi

NCOMMITS="$(git rev-list --count "${OLD}..${NEW}")"
FILES="$(git diff --name-only "${OLD}..${NEW}")"
count() { printf '%s\n' "${FILES}" | grep -cE "$1" || true; }
N_MIG="$(count '^apps/[^/]+/migrations/.+\.py$')"
N_STATIC="$(count '^static/')"
N_DEPS="$(count '^(pyproject\.toml|uv\.lock)$')"
N_TIMERS="$(count '^docs/scheduled-operations\.md$')"
echo "    ${OLD:0:7} -> ${NEW:0:7} (${NCOMMITS} commits)"
echo "    migraciones=${N_MIG} estaticos=${N_STATIC} dependencias=${N_DEPS} timers-doc=${N_TIMERS}"

# ---------------------------------------------------------------- 4
paso 4 "sudo (la contrasena la pide sudo por su TTY, una sola vez)"
sudo -v
( while true; do sleep 50; sudo -n -v 2>/dev/null || exit 0; done ) >/dev/null 2>&1 &
KEEP_PID=$!

# ---------------------------------------------------------------- 5
paso 5 "Entorno de produccion (deploy_status, sin imprimir valores)"
DS="$(manage deploy_status --json)"
settings_ok="$(jget "${DS}" "d.get('settings_module') == 'config.settings.prod'")"
db_ok="$(jget "${DS}" "d.get('db_path_ok') is True")"
PENDING0="$(jget "${DS}" "len(d.get('pending_migrations', []))")"
[[ "${settings_ok}" == "True" ]] || fail "el entorno no es de produccion (settings distinto de config.settings.prod)"
[[ "${db_ok}" == "True" ]] || fail "db_path_ok es falso: la base no es la esperada"
echo "    settings=prod: sí  db_path_ok: sí  migraciones ya pendientes en la VM: ${PENDING0}"

NEED_BACKUP=0
if [[ "${N_MIG}" -gt 0 || "${PENDING0}" -gt 0 || "${FORCE_BACKUP}" == "1" ]]; then NEED_BACKUP=1; fi

if [[ "${DRY}" == "1" ]]; then
  echo
  echo "=== RESUMEN"
  echo "DRY-RUN  ${OLD:0:7} -> ${NEW:0:7} (${NCOMMITS} commits); no se ejecuto nada"
  echo "plan: respaldo=$([[ ${NEED_BACKUP} == 1 ]] && echo sí || echo no)  pull  uv-sync=$([[ ${N_DEPS} -gt 0 ]] && echo sí || echo no)  migrate=$([[ ${N_MIG} -gt 0 || ${PENDING0} -gt 0 ]] && echo sí || echo no)  collectstatic=$([[ ${N_STATIC} -gt 0 ]] && echo sí || echo no)"
  echo "      reinicio  health  hash final"
  exit 0
fi

# ---------------------------------------------------------------- 6
BACKUP_NOTE="sin respaldo (sin migraciones)"
if [[ "${NEED_BACKUP}" == "1" ]]; then
  paso 6 "Respaldo ANTES del pull (con el codigo viejo)"
  manage backup
  BACKED_UP=1
  vb="$(manage verify_backup)"
  printf '%s\n' "${vb}"
  printf '%s\n' "${vb}" | grep -q 'restorable\.' || fail "verify_backup no dijo 'restorable.'"
  BACKUP_NOTE="respaldo restorable (verify_backup)"
else
  paso 6 "Respaldo: no hace falta (sin migraciones)"
fi

# ---------------------------------------------------------------- 7
paso 7 "git pull --ff-only"
PULLED=1
git pull --ff-only
[[ "$(git rev-parse HEAD)" == "${NEW}" ]] || fail "tras el pull HEAD no es ${NEW:0:7}"
echo "    HEAD = ${NEW:0:7}"

# ---------------------------------------------------------------- 8
SYNC_NOTE="sin cambios de dependencias"
if [[ "${N_DEPS}" -gt 0 ]]; then
  paso 8 "uv sync --no-dev --locked"
  sync_out="$("${UV}" sync --no-dev --locked 2>&1)"
  printf '%s\n' "${sync_out}"
  if printf '%s\n' "${sync_out}" | grep -qE 'Installed|Uninstalled'; then
    SYNC_NOTE="uv sync instalo paquetes"
  elif [[ "${ALLOW_NOOP}" == "1" ]]; then
    SYNC_NOTE="uv sync sin instalar nada (permitido)"
  else
    fail "uv sync no instalo nada con dependencias cambiadas (señal de despliegue fantasma; --allow-noop-sync si es esperado)"
  fi
else
  paso 8 "uv sync: no hace falta"
fi

# ---------------------------------------------------------------- 9
paso 9 "Migraciones"
DS1="$(manage deploy_status --json)"
PENDING1="$(jget "${DS1}" "len(d.get('pending_migrations', []))")"
MIG_NOTE="migraciones: 0 aplicadas, 0 pendientes"
if [[ "${PENDING1}" -gt 0 ]]; then
  MIGRATE_STARTED=1
  manage migrate --no-input
  DS2="$(manage deploy_status --json)"
  PENDING2="$(jget "${DS2}" "len(d.get('pending_migrations', []))")"
  if [[ "${PENDING2}" != "0" ]]; then
    apps="$(jget "${DS2}" "' '.join(sorted({m['app'] for m in d['pending_migrations']}))")"
    for a in ${apps}; do
      echo "--- showmigrations ${a}"
      manage showmigrations "${a}" | tail -n 6
    done
    fail "tras migrate quedan ${PENDING2} migraciones pendientes"
  fi
  MIG_NOTE="migraciones: ${PENDING1} aplicadas, 0 pendientes"
else
  echo "    sin migraciones pendientes"
fi

# ---------------------------------------------------------------- 10
STATIC_NOTE="collectstatic: no hacia falta"
if [[ "${N_STATIC}" -gt 0 ]]; then
  paso 10 "collectstatic"
  cs="$(manage collectstatic --no-input)"
  printf '%s\n' "${cs}"
  copied="$(printf '%s\n' "${cs}" | sed -nE 's/^([0-9]+) static files? copied.*/\1/p' | head -n 1)"
  [[ -n "${copied}" && "${copied}" -gt 0 ]] || fail "collectstatic copio ${copied:-0} archivos con estaticos cambiados"
  STATIC_NOTE="collectstatic: ${copied} copiados"
else
  paso 10 "collectstatic: no hace falta"
fi

# ---------------------------------------------------------------- 11
paso 11 "Reinicio del servicio"
sudo systemctl restart "${SERVICE}"
state=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
  state="$(systemctl is-active "${SERVICE}" || true)"
  [[ "${state}" == "active" ]] && break
  sleep $((1 * SLEEP_UNIT))
done
[[ "${state}" == "active" ]] || fail "el servicio esta '${state}' tras reiniciar"
echo "    active"

# ---------------------------------------------------------------- 12
paso 12 "Health"
code="$(wait_health)"
[[ "${code}" == "200" ]] || fail "health responde '${code}' en vez de 200 (rollback sugerido abajo; no se ejecuto)"
echo "    200"

# ---------------------------------------------------------------- 13
paso 13 "Hash final"
FINAL="$(git rev-parse HEAD)"
[[ "${FINAL}" == "$(git rev-parse origin/main)" ]] || fail "HEAD ${FINAL:0:7} no coincide con origin/main"

# ---------------------------------------------------------------- 14
paso 14 "Timers (aviso, no aborta)"
TIMER_COUNT="$(systemctl list-timers 'aerocontrol-*' --no-legend --no-pager 2>/dev/null | grep -c . || true)"
TIMER_NOTE="timers aerocontrol-*: ${TIMER_COUNT}"
echo "    ${TIMER_NOTE}"

echo
echo "=== RESUMEN"
echo "DEPLOY OK  ${OLD:0:7} -> ${FINAL:0:7} (${NCOMMITS} commits)"
echo "${MIG_NOTE}"
echo "${BACKUP_NOTE}"
echo "${SYNC_NOTE}"
echo "${STATIC_NOTE}"
echo "servicio: active  health: 200"
echo "${TIMER_NOTE}"
echo "HEAD == origin/main: sí"
if [[ "${N_TIMERS}" -gt 0 ]]; then
  echo "AVISO: cambio docs/scheduled-operations.md; los timers nuevos son del usuario (bloque mkjob)."
fi
