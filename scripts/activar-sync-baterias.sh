#!/usr/bin/env bash
#
# Activar el espejo de baterias de AeroLink en la VM (X.4b, LV-294).
#
# Se corre EN la VM, despues de desplegar AeroControl, y pide `sudo` una o dos veces:
# /etc/aerocontrol.env y /etc/systemd/system son de root.
#
#   cd /opt/aerocontrol && bash scripts/activar-sync-baterias.sh
#
# Idempotente: se puede repetir. Cada paso comprueba antes de cambiar, y **el timer se
# instala al final y sólo si la simulacion salio bien** -- un timer sobre un sync que no
# funciona seria un vigilante escribiendo a Direccion por algo que nadie probo.
#
# Nunca imprime el token: se copia de /opt/aerolink/.env a /etc/aerocontrol.env sin
# pasar por la pantalla ni por el historial.

set -euo pipefail

ROOT=/opt/aerocontrol
ENV_FILE=/etc/aerocontrol.env
ACL_ENV=/opt/aerolink/.env
UV=/home/levdigital01/.local/bin/uv
TIMER=aerocontrol-sync-batteries

paso() { printf '\n==> %s\n' "$1"; }

# Los comandos de manage.py corren **como corren los timers**: systemd lee el
# EnvironmentFile como root y baja a levdigital01. Un `sudo -u levdigital01 bash -c
# '. /etc/aerocontrol.env'` fallaria: ese usuario no puede leer el archivo.
manage() {
  sudo systemd-run --quiet --wait --pipe --collect \
    --uid=levdigital01 \
    -p WorkingDirectory="${ROOT}" \
    -p EnvironmentFile="${ENV_FILE}" \
    "${UV}" run python manage.py "$@"
}

paso "0. AeroLink responde en esta VM"
code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health || true)"
if [[ "${code}" != "200" ]]; then
  echo "ERROR: AeroLink no responde en 127.0.0.1:8081 (HTTP ${code:-sin respuesta})." >&2
  echo "Sin eso no hay nada que espejar. Ver docs/operations/DEPLOY_P340.md de AeroLink." >&2
  exit 1
fi
echo "    /health -> 200"

paso "1. Variables AEROLINK_* en ${ENV_FILE}"
if sudo grep -q '^AEROLINK_API_TOKEN=' "${ENV_FILE}"; then
  echo "    ya estan; no se tocan"
else
  # El token se lee y se escribe **dentro** del mismo `sudo sh -c`: no sale a la pantalla.
  sudo sh -c "printf 'AEROLINK_API_URL=http://127.0.0.1:8081/api/v1\nAEROLINK_API_TOKEN=%s\n' \
    \"\$(grep -E '^SERVICE_TOKEN=' ${ACL_ENV} | cut -d= -f2-)\" >> ${ENV_FILE}"
  echo "    agregadas"
fi
n="$(sudo grep -c '^AEROLINK_' "${ENV_FILE}")"
if [[ "${n}" != "2" ]]; then
  echo "ERROR: se esperaban 2 variables AEROLINK_* y hay ${n}. Revisar ${ENV_FILE} a mano." >&2
  exit 1
fi
echo "    AEROLINK_*: ${n} (valores no mostrados)"

paso "2. audit_serial_case (sólo lectura): ¿hay seriales que difieran sólo por mayúsculas?"
manage audit_serial_case

paso "3. sync_batteries --dry-run: no escribe nada"
manage sync_batteries --dry-run
cat <<'AVISO'

    Con el inventario de AeroLink vacio esto dice "0 created, 0 updated" y es correcto,
    pero NO prueba que el sync funcione. Eso se prueba cuando haya baterias cargadas.
AVISO

paso "4. El timer (05:45 UTC, antes de generate_alerts)"
if systemctl list-unit-files "${TIMER}.timer" --no-legend 2>/dev/null | grep -q "${TIMER}"; then
  echo "    ${TIMER}.timer ya existe; no se reescribe"
else
  sudo tee "/etc/systemd/system/${TIMER}.service" >/dev/null <<EOF
[Unit]
Description=AeroControl ${TIMER#aerocontrol-}
After=network.target

[Service]
Type=oneshot
User=levdigital01
WorkingDirectory=${ROOT}
EnvironmentFile=${ENV_FILE}
ExecStart=${UV} run python manage.py sync_batteries
EOF
  sudo tee "/etc/systemd/system/${TIMER}.timer" >/dev/null <<EOF
[Unit]
Description=AeroControl ${TIMER#aerocontrol-} (scheduled)

[Timer]
OnCalendar=*-*-* 05:45:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now "${TIMER}.timer"
  echo "    instalado y activo"
fi

paso "5. Comprobar"
systemctl list-timers "${TIMER}.timer" --no-pager

echo
echo "LISTO. Mientras el timer no existia, check_scheduled_jobs leia sync_batteries como"
echo "'nunca corrio'; desde ahora corre solo. Para probarlo ya, con baterias cargadas:"
echo "    sudo systemctl start ${TIMER}.service && journalctl -u ${TIMER}.service -n 20 --no-pager"
