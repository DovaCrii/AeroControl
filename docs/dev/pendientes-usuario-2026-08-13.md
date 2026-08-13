# Los cinco pendientes que no dependen del código — listos para ejecutar

Nota interna (`docs/dev/`, no autoritativa). Se borra cuando estén los cinco.

Ninguno de estos se resuelve escribiendo código: dependen de un dato que sólo
está en la DGAC, de una variable de entorno en la VM, de un disco compartido o
de un clic en GitHub. Lo que sí se puede hacer desde acá —y es lo que hay abajo—
es dejar cada uno reducido a un comando o un clic, con lo verificado ya
verificado.

---

## 1. Las 10 vigencias (`LV-74`) — parcialmente resuelto acá

**Hallazgo:** `load_dgac_vigencias` ya trae una tabla transcrita de las capturas
SIGO del 2026-08-03, y **una de las tres aeronaves que faltan ya está en ella**:

| Aeronave | ¿Está la fecha en el repo? |
|---|---|
| `RPA-3696` | **Sí** — `2026-12-21` |
| `RPA-2019` | No |
| `RPA-7126` | No |

Los 7 operadores no se pueden cruzar desde acá: la tabla usa el **número de
credencial DGAC** como llave y el `HANDOFF` los nombra por nombre. El comando lo
resuelve solo, y **reporta las llaves que no calzan en vez de inventarlas**.

**Qué correr en `p340`** (después del despliegue, con el entorno cargado):

```bash
uv run python manage.py load_dgac_vigencias --dry-run
```

Eso imprime qué cambiaría y qué llaves no calzan, **sin escribir**. Si lo que
propone es correcto:

```bash
uv run python manage.py load_dgac_vigencias
```

Es idempotente: sólo escribe las dos fechas, así que repetirlo no hace daño.

**Lo que quedará faltando igual** son las vigencias que no están en ninguna
captura (al menos `RPA-2019` y `RPA-7126`). Para esas, dos caminos: cargarlas a
mano desde la ficha de cada aeronave, o hacer una captura nueva de SIGO y pasarla
por CSV:

```bash
uv run python manage.py load_dgac_vigencias --file vigencias.csv --dry-run
```

```csv
kind,key,expiry
aircraft,RPA-2019,2027-01-15
aircraft,RPA-7126,2027-03-20
operator,12345,2027-08-01
```

`key` es la matrícula para aeronaves y el **número de credencial DGAC** para
operadores (con el nombre completo como respaldo).

> **Por qué importa más que el resto de esta lista:** un `NULL` **no genera
> alerta** (decisión de `LV-29`: un nulo significa "nunca se ingresó"). Así que
> estas 10 son invisibles para las alertas, el calendario y el reporte — el hueco
> no se anuncia solo. Es el único pendiente con impacto de cumplimiento hoy.

---

## 2. `CSP_REPORT_ONLY=False` — criterio de salida de beta

Verificado en demo con cero violaciones. En `/etc/aerocontrol.env` de la VM:

```bash
sudo sh -c 'echo "CSP_REPORT_ONLY=False" >> /etc/aerocontrol.env'
sudo systemctl restart aerocontrol
```

Comprobar que quedó **enforcing** (debe aparecer `Content-Security-Policy`, sin
el sufijo `-Report-Only`):

```bash
curl -sI https://<host>/accounts/login/ | grep -i content-security-policy
```

> **Ojo con una excepción legítima:** el visor de documentos (`LV-85`) responde
> `frame-ancestors 'self'` **sólo en su propia respuesta**; el resto del sitio
> sigue en `'none'`. Si al pasar a enforcing algo deja de verse, mirar primero
> ahí antes de aflojar la política global.

---

## 3. El antivirus (`DOCUMENTS_ANTIVIRUS_COMMAND`) — más urgente desde `LV-86`

Está **vacío en todos los ambientes**, y la carga masiva multiplica archivos
entrando al sistema. El código espera un ejecutable compatible con ClamAV: lo
resuelve con `shutil.which()` y lo invoca **sin shell**, con
`<comando> --no-summary <archivo>`.

```bash
sudo apt install -y clamav clamav-daemon
sudo systemctl stop clamav-freshclam && sudo freshclam && sudo systemctl start clamav-freshclam
sudo sh -c 'echo "DOCUMENTS_ANTIVIRUS_COMMAND=clamscan" >> /etc/aerocontrol.env'
sudo systemctl restart aerocontrol
```

Comprobar que el ejecutable existe **para el usuario del servicio**, que es lo
que `shutil.which()` va a mirar:

```bash
sudo -u levdigital01 which clamscan
```

> Si el comando queda configurado pero **no existe**, la subida falla con
> "Configured antivirus command is not available" en vez de aceptar el archivo
> sin escanear. Eso es a propósito: falla cerrado.

---

## 4. Los 2 nombres de carpeta en `Z:` (`R4.1a`)

Verificado en `Z:\01-116 OPERACIONES_RPA_JEJ` el 2026-08-13. Los dos nombres
equivocados **siguen ahí**:

| Actual | Correcto | Qué está mal |
|---|---|---|
| `CC684-1581F5FHC246BOOD7WPK-M3E` | `CC684-1581F5FHC246B00D7WPK-M3E` | lleva **letra O** donde van **ceros** (`RPA-4647`) |
| `CC717-1582F5FHC24BB00DMXNH-M3E` | `CC717-1581F5FHC24BB00DMXNH-M3E` | empieza en **1582**, debe ser **1581** (`RPA-4884`) |

El segundo está confirmado por la captura de SIGO, que muestra
`1581F5FHC24BB00DMXNH` para la inscripción 4884.

```powershell
Rename-Item "Z:\01-116 OPERACIONES_RPA_JEJ\CC684-1581F5FHC246BOOD7WPK-M3E" "CC684-1581F5FHC246B00D7WPK-M3E"
Rename-Item "Z:\01-116 OPERACIONES_RPA_JEJ\CC717-1582F5FHC24BB00DMXNH-M3E" "CC717-1581F5FHC24BB00DMXNH-M3E"
```

> **Por qué no lo hace el agente:** `AGENTS.md` y `R4.1a` fijaron que **`Z:` no se
> toca desde este repo** — es el repositorio documental de la empresa, compartido,
> y el nombre de una carpeta puede estar referenciado en otro lado. La corrección
> es del usuario; acá sólo se dejó verificado cuáles son y a qué deben quedar.

Con los dos corregidos, **las 16 aeronaves calzan** y `R4` deja de estar
bloqueado por el calce (sigue esperando el antivirus del punto 3 para `--apply`).

---

## 5. El PR en AeroLink

La rama `codex/api-inventario-dispositivos` está **pusheada, verde y sincronizada**
con su origin: 1 commit, 18 archivos, 1.128 líneas, con 51 tests. Su `main` no se
movió desde entonces, así que no hay conflicto.

Sólo falta abrir el PR (su `main` está protegido). **No se puede desde acá**: los
conectores de GitHub necesitan autorización y esta sesión es no interactiva.

<https://github.com/DovaCrii/AeroLink/compare/main...codex/api-inventario-dispositivos>

**Título sugerido:**

```
feat(api): AL-107 inventario de dispositivos para AeroControl
```

**Cuerpo sugerido** (el mensaje del commit ya lo explica; lo esencial para quien
revise):

> Cierra la mitad de la fase 2 del ADR-0002 que **no** depende de las sesiones de
> vuelo: AeroControl ya tiene su consumidor implementado y probado, faltaba el
> productor.
>
> - `GET /api/v1/devices/?kind=battery` — sólo lo que AeroLink masterea.
>   `kind=aircraft` responde **403 citando AL-R4**, que convierte "no duplicar el
>   padrón" en una aserción que una prueba verifica.
> - **Falla cerrado**: sin token configurado responde **503**, nunca 401 ni lista
>   vacía — el consumidor convierte cualquier no-200 en trabajo fallido, y una
>   lista vacía sería indistinguible de un inventario realmente vacío.
> - Ciclos, salud y firmware desde `metadata_json`, no columnas nuevas: la tabla
>   está vacía hasta AL-203 y aún no se ha visto un payload DJI real. El esquema
>   de respuesta es el contrato; el almacenamiento es detalle.
> - Abre con el **ADR-0003** antes que con el endpoint, porque `AGENTS.md` dejaba
>   la integración fuera de alcance "hasta crear un plan separado".
> - **Verificado de punta a punta**: AeroControl sincronizó 2 baterías contra el
>   endpoint real y enlazó una a `RPA-2002` por número de serie.

---

## Qué sigue bloqueado, y por qué

| Pendiente | Bloqueado por |
|---|---|
| 1 (vigencias) | la VM (caída) + los datos de `RPA-2019` y `RPA-7126`, que no están en ninguna captura |
| 2 (CSP) y 3 (antivirus) | acceso SSH a producción |
| 4 (`Z:`) | decisión vigente: `Z:` no se toca desde este repo |
| 5 (PR) | GitHub sin autorizar en esta sesión |
