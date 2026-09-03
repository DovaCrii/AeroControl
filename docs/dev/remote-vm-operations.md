# Acceso remoto a la VM AeroControl

> **Cómo llegó este archivo acá.** Vivía **sólo en `/opt/aerocontrol` de la VM**,
> sin versionar: cualquier limpieza del árbol lo borraba, y la única copia estaba
> en la máquina que documenta. Se versionó el 2026-08-28, reconciliando dos
> puntos donde contradecía hallazgos ya verificados — están marcados abajo.

Esta guía permite administrar AeroControl desde un notebook u otro equipo sin
abrir puertos de la red corporativa. La VM se expone sólo dentro de Tailscale.

## Datos de la VM

| Concepto | Valor |
| --- | --- |
| Nombre Ubuntu | `p340` |
| Dirección Tailscale | `100.121.16.118` |
| Aplicación | `https://p340.tailccd107.ts.net` |
| Usuario Linux | `levdigital01` |
| Código de la app | `/opt/aerocontrol` |
| Datos persistentes | `/srv/aerocontrol-data` |

> **El nombre DNS `p340.tailccd107.ts.net` no sirve para SSH.** La versión
> original de este documento lo usaba; el `HANDOFF` registra que **resuelve a una
> IP pública ajena**, así que para conectarse va la IP de Tailscale. Para el
> navegador el nombre sí funciona, porque ahí lo resuelve el propio Tailscale.

No uses la cuenta de AeroControl para SSH: es distinta de la cuenta Linux.

## 1. Conectar un notebook al tailnet

1. Instala Tailscale desde <https://tailscale.com/download>.
2. Inicia sesión con la **misma cuenta/tailnet que contiene `p340`**, o pide al
   administrador de ese tailnet que invite tu cuenta o comparta la VM.
3. Confirma en PowerShell:

   ```powershell
   tailscale status
   ```

   Debe aparecer `p340`. Si no está, el equipo está conectado a otro tailnet; no
   es un problema de la VM.

## 2. Acceso SSH con llave

```powershell
ssh -i "$env:USERPROFILE\.ssh\aerocontrol_vm_notebook" levdigital01@100.121.16.118
```

La primera vez acepta la huella de host sólo si corresponde a `p340`. Después de
verificar que la llave funciona, evita el acceso por contraseña. Si se pierde un
notebook, elimina **únicamente su línea** de `~/.ssh/authorized_keys` desde la
VM: las llaves son por equipo justamente para poder revocar una sin tocar las
demás.

## 3. Verificación rápida

```bash
systemctl is-active aerocontrol
```

```bash
tailscale serve status
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://p340.tailccd107.ts.net/health/
```

El servicio debe indicar `active` y el endpoint de salud devolver `200`.

## 4. Publicar cambios

> **El procedimiento de despliegue vive en un solo lugar: `HANDOFF.md` → "Cómo
> desplegar".** La versión original de este documento traía su propio bloque, y
> **le faltaba el respaldo y su verificación antes del `migrate`**. Dos
> procedimientos que difieren no son redundancia: son la forma en que un paso se
> pierde, y el 2026-08-28 el respaldo estuvo a punto de saltarse por menos que
> eso. Lo que sigue acá es sólo lo propio del acceso remoto.

Antes de actualizar, **anota el commit actual** — es a lo que se vuelve si algo
sale mal:

```bash
cd /opt/aerocontrol && git rev-parse --short HEAD
```

Y confirma qué vas a traer antes de traerlo:

```bash
git fetch origin && git log --oneline HEAD..origin/main
```

## 5. Reversión segura

Si una actualización falla, **no borrar datos**. Detener y mirar el log:

```bash
sudo journalctl -u aerocontrol -n 100 --no-pager
```

La reversión de código va a un commit **conocido y compatible con las
migraciones ya aplicadas**; `git reset --hard` no es la primera respuesta. Y
volver con `git checkout <commit>` deja la VM en **HEAD desprendido**: si se
hace, hay que volver a `main` el mismo día, o los `git pull` posteriores fallan
en silencio y el despliegue parece exitoso sin serlo (pasó, y está documentado
en `AGENTS.md`).

## Seguridad mínima

- Mantén Tailscale conectado sólo a cuentas autorizadas.
- La aplicación no necesita puertos abiertos en el router ni en la LAN.
- `/etc/aerocontrol.env` contiene secretos: sigue como `root:root`, modo `600`.
  **Nunca lo copies al notebook ni al repositorio.**
- Rota la contraseña de sudo/SSH usada durante la instalación y conserva las
  llaves SSH **por equipo**, no compartidas.
