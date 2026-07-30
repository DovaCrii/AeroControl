# Acceso público con Tailscale Funnel

Complemento del [runbook de la VM](ubuntu-vm-deploy.md). El runbook levanta
AeroControl **solo dentro del tailnet** (`tailscale serve`, sin exposición a
internet). Este documento describe cómo **exponer la app a internet** con
Tailscale Funnel, sobre el mismo dominio `https://p340.tailccd107.ts.net`, sin
abrir puertos del router y sin que el visitante tenga Tailscale.

> **Cuándo usar esto.** Solo cuando alguien que **no** puede entrar al tailnet
> necesita usar la app (editar, cargar, revisar). Si la persona puede instalar
> Tailscale, es preferible compartirle la VM (*Machines → p340 → Share…*) y
> **no** abrir Funnel. Funnel deja el login expuesto a todo internet.

## Requisito previo obligatorio: login endurecido

Funnel pone el formulario de login de cara a internet. **No abrir Funnel sin el
bloqueo de fuerza bruta** (`django-axes`), incorporado en el commit
`fea3f3c` (MASTER_PLAN T2.5 / F-17-F-18): 5 intentos fallidos por usuario →
bloqueo 15 min, ajustable por entorno (`AXES_FAILURE_LIMIT`,
`AXES_COOLOFF_MINUTES`). La app ya trae además HTTPS + HSTS, cookies seguras,
CSP, sesión que caduca al cerrar el navegador (tope 12 h) y permisos por rol.

## 1. Habilitar el atributo `funnel` en la policy (panel web de Tailscale)

En <https://login.tailscale.com/admin/acls>, agregar (si no existe) el bloque
`nodeAttrs`:

```json
"nodeAttrs": [
  { "target": ["autogroup:member"], "attr": ["funnel"] }
]
```

Sin este atributo, el comando de la sección 2 falla e imprime justo estas
instrucciones.

## 2. Activar Funnel en la VM

La app escucha en `127.0.0.1:8000` (gunicorn detrás de Tailscale). En esta
versión de Tailscale la CLI de serve/funnel cambió; el comando correcto es:

```bash
sudo tailscale funnel --bg 8000
```

`--bg` lo deja corriendo en segundo plano. Requiere `sudo` porque el nodo no
tiene `operator` configurado. Verificar:

```bash
tailscale funnel status
```

Debe mostrar `https://p340.tailccd107.ts.net` como **Funnel on** (ya no
"tailnet only") apuntando a `http://127.0.0.1:8000`.

## 3. Verificar desde fuera del tailnet

Comprobar desde un equipo **sin** Tailscale (p. ej. un teléfono con datos
móviles, no en la WiFi de la oficina): abrir `https://p340.tailccd107.ts.net/`
→ debe salir el login. Un equipo que ya está en el tailnet llega igual con o sin
Funnel, así que no sirve para verificar la exposición pública.

## 4. Crear la cuenta de la persona

Como `root`, en `https://p340.tailccd107.ts.net/admin/` → **Users → Add user**,
contraseña fuerte, y asignar su grupo de rol (`Operations`, `Compliance`,
`Maintenance`, `Viewer`, `Dirección` o `Administrator`). No marcar *superuser*
salvo que se quiera dar acceso total.

## 5. Revertir (volver a solo-tailnet)

```bash
sudo tailscale funnel reset          # quita Funnel (deja de ser público)
sudo tailscale serve --bg 8000       # restaura el acceso solo-tailnet
tailscale serve status               # debe decir "tailnet only"
```

## Notas de seguridad

- Mientras Funnel esté activo, `/health/` y el login son públicos. El bloqueo de
  axes es la principal defensa del login; usar contraseñas fuertes.
- El `access log` de axes (`axes_accesslog` / `axes_accessattempt`) registra la
  IP reenviada (`X-Forwarded-For`) para forense, aunque el bloqueo se llave por
  usuario (ver el porqué en `config/settings/base.py`).
- No hace falta tocar `ALLOWED_HOSTS` ni `CSRF_TRUSTED_ORIGINS`: el dominio
  público es el mismo `*.ts.net` que ya se usa en el tailnet.
- Si en el futuro se quiere un dominio propio o un WAF, evaluar Cloudflare
  Tunnel en vez de Funnel.
