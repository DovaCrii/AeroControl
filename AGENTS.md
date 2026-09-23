# AeroControl — guía para agentes (Codex / Claude Code)

## Objetivo

Aplicación Django local-first para coordinar operaciones de aviación (flota RPA/UAS, operadores, cumplimiento DGAC, mantenimiento, permisos de vuelo, Kanban). La seguridad, trazabilidad y consistencia de datos prevalecen sobre cambios cosméticos. El proyecto está en **pausa de estabilización**: no se agrega funcionalidad nueva fuera de lo definido en `MASTER_PLAN.md` sin que el usuario lo pida explícitamente.

**Decisión de despliegue ya tomada (no reabrir sin que el usuario lo pida):** la aplicación se mantiene como web en servidor interno (intranet), no como app de escritorio. PostgreSQL se adopta cuando haya usuarios concurrentes reales (ver `docs/postgresql-readiness.md`); no migrar antes.

> **Si existe `HANDOFF.md` en la raíz, léelo antes que nada.** Describe una
> situación puntual sin resolver (por ejemplo un merge pendiente) que condiciona
> lo que se puede hacer. Se borra cuando queda resuelta; su ausencia significa
> que no hay nada excepcional y se puede ir directo a `MASTER_PLAN.md`.

## Trabajo en paralelo

Puede haber **otra sesión de agente empujando a la misma rama**. Ocurrió el
2026-07-24: dos líneas arreglaron el mismo P0 por separado. Por eso:

- `git fetch` **antes** de cualquier push, y revisar `git log HEAD..origin/<rama>`.
- Si la rama divergió, **nunca** `push --force`: empuja a una rama nueva o
  fusiona deliberadamente. Sobrescribir el trabajo de otro no es reversible.
- Al fusionar, `locale/es/LC_MESSAGES/django.mo` es **binario**: no se resuelve a
  mano, se regenera con `scripts/compile_translations.py` desde el `.po` fusionado.

## Precedencia documental

Cuando dos documentos parezcan contradecirse, este es el orden de autoridad:

`AGENTS.md` (este archivo) > `MASTER_PLAN.md` (qué hacer y en qué orden) > `openspec/changes/*` (spec del bloque en curso) > `AUDIT_CLAUDE.md` (evidencia técnica) > `BACKLOG.md` (registro histórico) > `README.md` / `ARCHITECTURE.md` > `docs/*.md` > `docs/dev/*.md` (notas internas, no autoritativas — pueden estar desactualizadas).

Si un plan externo (por ejemplo un archivo que el usuario suba fuera del repo) propone una convención que choca con lo ya establecido aquí — nombres de rama, umbrales, estructura de carpetas — se reconcilia a favor de lo ya vigente en el repo, y se deja constancia del ajuste en el PR o en `MASTER_PLAN.md`, no se cambia esta guía en silencio.

## Flujo de trabajo Git

- `main` siempre desplegable. Nunca se modifica directamente.
- Una rama por bloque de trabajo: `codex/<area-o-bloque>` (p. ej. `codex/repo-hygiene`, `codex/alertas-kanban`). No usar `feat/...` ni otros prefijos — esta es la convención real del repo.
- Un PR por bloque, con CI verde. No mezclar bloques ni intenciones distintas en el mismo PR/commit (ver deuda histórica del commit `980b763` en `AUDIT_CLAUDE.md`, que mezcló tooling vendorizado con correcciones de traducción — no repetir ese patrón).
- Usa `uv sync --all-groups` al empezar. Antes de entregar, `scripts/verify.ps1` debe pasar completo (ver sección de calidad).
- Define `DB_PATH`, `DOCUMENTS_DIR`, `LOGS_DIR` y `BACKUPS_DIR` fuera del repositorio. Nunca confirmes datos operativos, documentos, backups ni secretos reales.
- Para cambios de modelo, crea y revisa la migración generada (nombre descriptivo, no el autogenerado por Django si es ambiguo); incluye pruebas de regresión para la regla de negocio que motiva el cambio.
- Cada bloque cerrado actualiza `MASTER_PLAN.md` (marcar la tarea ✅), añade su entrada a `CHANGELOG.md` (`[Unreleased]`) y, si corresponde, `BACKLOG.md`.

## Convenciones de dominio (no negociables)

- `apps.core.BaseModel`: UUID como PK, `created_at`/`updated_at`, `is_active` para archivado lógico — **nunca borrar filas operativas**, archivar. `notes` para contexto opcional.
- ForeignKeys operativos usan `on_delete=PROTECT` salvo justificación explícita documentada en el PR (ver `AUDIT_CLAUDE.md` F-07 sobre los `CASCADE` que hay que corregir — no introducir más).
- Lógica de negocio en modelos ("fat models, thin views"). Nada de reglas de negocio en templates, forms-only (sin espejo en `clean()`/constraint) ni serializers — ver `ARCHITECTURE.md`.
- Interfaz bilingüe ES/EN: todo string visible al usuario usa `gettext`/`gettext_lazy`, nunca texto crudo ni `_(variable)` (no extraíble por `makemessages`). **Las cadenas fuente se escriben en inglés**; el español vive en el catálogo, nunca en el código.
- **El español del catálogo es neutral, sin voseo.** Nada de *"podés"*, *"escribí"*, *"emití"*, *"revisá"*, *"volvé"*: ese registro es rioplatense y la organización es chilena, así que suena prestado. Preferir el impersonal (*"ya se puede escribir"*, *"conviene revisar"*) y, cuando haya que dirigirse a la persona, el trato de usted (*"¿No puede entrar?"*, *"escriba a…"*, *"vuelva a probar"*). Se coló en ocho cadenas el 2026-09-02 y **lo detectó el usuario, no un test**: el guardián de traducciones comprueba que no falten, que no estén vacías ni *fuzzy* y que las fuente estén en inglés — el registro no lo mira nadie.
- **GNU gettext es obligatorio** (`scoop install gettext` en Windows, `apt install gettext` en Linux). Sin él `makemessages` no corre y el catálogo se desincroniza en silencio: así se acumularon 29 cadenas rotas y 26 msgid duplicados que impedían a `msgmerge` funcionar. El flujo es `makemessages -l es` → traducir → `compilemessages -l es`. `scripts/compile_translations.py` solo compila; **no valida ni extrae**, así que no sustituye a gettext.
- En producción los estáticos llevan hash de contenido (`STORAGES` en `prod.py`), así que `collectstatic` es **obligatorio** antes de servir: sin `staticfiles.json` toda etiqueta `{% static %}` falla. `build.sh` ya lo ejecuta. En desarrollo se usa el almacenamiento por defecto, para no tener que correr `collectstatic` antes de cada `runserver`.
- `apps/core/test_translations.py` vigila la deriva sin depender de gettext: falla si hay msgid duplicados, entradas vacías o *fuzzy* (Django ignora las fuzzy, así que salen en inglés), cadenas del código ausentes del catálogo, diferencias de solo mayúsculas, o cadenas fuente escritas en español.
- Auditoría: toda mutación autenticada relevante debe quedar en `AuditEvent` (append-only) vía `apps.core.audit.set_audit_context` en la vista.

## Contrato de permisos y lectura (obligatorio en toda vista nueva)

- Vistas mutantes (crear/editar/borrar/transición de estado) exigen el permiso `add_*`/`change_*`/`delete_*` correspondiente.
- **Toda vista de lectura (listado, detalle, exportación, API) exige `view_*` explícito** — no basta `LoginRequiredMixin` a secas. Este es el gap que produjo los hallazgos F-05/F-06 de `AUDIT_CLAUDE.md` (documentos y calendario legibles sin permiso de dominio); no repetirlo.
- Si el modelo tiene o debería tener aislamiento por `tenant`/`OperationalTenant`, la vista debe acotar el queryset por tenant del usuario, no solo por permiso de modelo (ver F-08 sobre el estado real, hoy incompleto, de esa garantía).
- **Toda vista nueva debe tener una prueba de 403** para un usuario sin el permiso correspondiente, y si aplica, una prueba de aislamiento cross-tenant.
- No uses `fields = "__all__"` en formularios de escritura.
- Valida relaciones de dominio en formularios **y** en modelos (`clean()` o `CheckConstraint`) — no solo en el formulario, que es evadible desde el admin, la API o un import.
- No interpoles JSON controlado por usuarios con `|safe`; usa `json_script`.
- Las exportaciones (CSV/XLSX/DOCX) deben neutralizar fórmulas y limitar campos a datos aprobados — reutiliza `CsvExportMixin`, no reimplementes la neutralización.

## Definition of Done por tipo de cambio

| Tipo de cambio | Mínimo exigido |
|---|---|
| Modelo nuevo/campo nuevo | Migración con nombre descriptivo + `CheckConstraint`/`UniqueConstraint` si aplica + prueba de la constraint |
| Vista nueva | Prueba de 403 sin permiso + prueba de scope de tenant si el modelo lo requiere + strings traducidos |
| Comando de management | Prueba de camino feliz + prueba de camino de error (no solo `CommandError` trivial) |
| Formulario | Prueba por cada regla de `clean()`/`add_error` |
| Corrección de bug | Prueba que falla sin el fix y pasa con él (ver commits `7dc4151`/`86c57ce` como ejemplo) |
| Cambio de plantilla | Confirmar que `apps/core/test_templates.py` sigue verde (compila) |

## Calidad obligatoria antes de cada commit/PR

Gate canónico (debe pasar completo, y ahora sí falla si algo se rompe — ver `scripts/verify.ps1`):

```powershell
pwsh scripts/verify.ps1
```

Para iterar rápido dentro de una app, sin esperar el gate completo:

```powershell
uv run pytest apps/<app>/tests.py
uv run ruff check .
```

El gate completo corre: `manage.py check` (+ `--deploy`), `makemigrations --check --dry-run`, `pytest -n auto --cov=apps` (falla bajo el umbral de `pyproject.toml`, hoy 83%), `ruff check`, `ruff format --check`, `bandit`, `pip-audit`.

**La suite corre en paralelo** (`-n auto`, un proceso por núcleo, desde `LV-256`). Cada worker tiene su propia base, así que las filas no se cruzan; lo que sí se cruzaría es **disco fuera de `tmp_path`** y **estado de proceso** (cachés de módulo, variables globales). Un test nuevo que escriba archivos usa `tmp_path` y apunta `settings.DOCUMENTS_ROOT` ahí, como `test_lv200_step2_the_file_is_reused`; y un techo de consultas calienta la caché de `ContentType` antes de medir, como `test_lv237_panel_query_budget`. Para depurar un fallo que sólo aparece en paralelo, correr ese archivo solo y sin `-n`: si ahí pasa, la causa es compartida.

## Lecciones operativas (gotchas verificados, no teoría)

Cada una costó tiempo real al menos una vez. Consolidadas 2026-08-11.

**El tablero miente en las dos direcciones.** Un `⬜` puede estar hecho: pasó con `T2.1`, con `R1.1`/`R1.2`/`R1.3` (resueltos 4 días antes de que alguien marcara la casilla), con `X.2` y con `V.3` — cinco veces. **Antes de implementar una fila pendiente, grep el código que describe.** Puede ahorrar la implementación entera. Y al revés: una fila ✅ puede tener una premisa vencida (la de `R6.4` decía "sólo existe como correo" cuando la vista web ya existía).

**`makemessages` fuzzy-matchea mal y no avisa.** Inventa traducciones tomándolas de strings parecidos. Después de **cada** corrida: `grep fuzzy` en el `.po`, corregir a mano, y recompilar el `.mo` con `polib` — **el despliegue no corre `compilemessages`** y el `.mo` está versionado, así que un `.po` correcto con `.mo` viejo se ve en inglés en producción. `test_every_entry_is_translated_and_not_fuzzy` lo caza; confía en ese cero, no en una revisión visual.

**Los strings fuente van en inglés.** `test_source_strings_are_written_in_english` falla con una sola tilde en un literal del código. Escribí el `msgid` en inglés y la versión española en el catálogo, incluso para textos que sólo verá un usuario chileno.

**Correr `ruff check` *y* `ruff format --check`.** El CI corre ambos y ya estuvo rojo días porque una sesión sólo corrió el primero.

**Verificar en el navegador antes de marcar ✅.** Los tests pasan y la pantalla igual está mal — o al revés, la fila del tablero describe un problema que ya no existe. El demo (`scripts/run-demo.ps1`, login `demo`/`demo-review-only`) tiene datos con casos límite que la copia de restauración no tiene: el bug de orden de operaciones de la migración `0028` era **silencioso** contra la copia limpia y reventó contra el demo.

**Señales: `post_save`, no `pre_save`, cuando el handler vuelve a guardar algo.** `Alert.resolve()` re-guarda la tarjeta enlazada; con `pre_save` esa escritura interna corre contra el guardado externo que aún no aterrizó y se pierde. Lo atrapó un test que falló (R6.1), no una revisión.

**Un `⬜` bloqueado por una decisión de negocio no se desbloquea programando.** Umbrales de contrato, límites de jornada y metas de KPI los define el usuario; inventar un número convierte un control en un estorbo que alguien va a desactivar.

**Producción: dónde corre cada comando.** El merge/push va en Windows (las ramas sólo existen ahí); el despliegue va **dentro** de la sesión SSH (`/opt/aerocontrol` es ruta Linux y PowerShell la resuelve como `C:\opt\...`). Al cargar el entorno en la VM, **`set -a` no es opcional**: `source` sobre un archivo `CLAVE=valor` define variables de shell, no de entorno, y `manage.py` cae a `config.settings.dev`. Verificá `DJANGO_SETTINGS_MODULE` y `DB_PATH` con un `echo` **antes** de migrar.

**Un rollback deja la VM en HEAD desprendido, y ahí `git pull` no despliega nada.** El procedimiento de rollback es `git checkout <commit-anterior>`, que deja `p340` sin rama. Todo `git pull` posterior falla con *"You are not currently on a branch"* y el despliegue **parece** correr: `uv sync`, `collectstatic` y el `restart` se ejecutan sobre el código viejo y no devuelven error. Pasó el 2026-08-27: dos tandas (2026-08-26 y 2026-08-27) se dieron por desplegadas sin estarlo. **El primer comando de todo despliegue es `git status --short --branch`**, y la primera línea tiene que decir `## main...origin/main`, no `## HEAD (no branch)`. Después de un rollback, volver con `git checkout main` **el mismo día**. Al terminar, `git log --oneline -1` en la VM tiene que coincidir con el `main` que pusheaste — es la única prueba de que llegó.

**Versionar un archivo que ya existe *sin versionar* en la VM bloquea el `git pull`.** Git se niega —"untracked working tree files would be overwritten by merge"— y aborta. Lo peligroso es lo que viene después: `uv sync`, `migrate` y `collectstatic` corren igual, sobre el código viejo, y **cada uno responde algo plausible**. Pasó el 2026-08-28 con `docs/dev/remote-vm-operations.md`: el `sync` dijo "Checked 64 packages" sin instalar nada, el `migrate` dijo "No migrations to apply" y el `collectstatic` copió 0 archivos — tres silencios que, con un salto de Django y dos migraciones esperando, eran la prueba de que no había llegado nada. **Antes de versionar un archivo que vive en la VM, apartarlo allá primero** (`mv` a `~`, no `rm`, y comparar con `diff` después). Y las tres señales de un despliegue que no llegó: `[behind N]` en el `status`, `uv sync` sin instalar y `migrate` sin aplicar.

**El bloque de despliegue va con `&&`, y `set -a; source ...; set +a` lo rompe.** Los `;` que necesita la carga del entorno cortan la cadena, así que un `git pull` fallado no frena el `restart` que viene después. Pegar el despliegue **por pasos**, mirando la salida de cada uno, en vez de una sola línea encadenada: el one-liner convierte un fallo visible en un despliegue fantasma.

**Una fila fantasma es el espejo de un despliegue fantasma: el trabajo hecho y el registro sin hacer.** `LV-186` se implementó, pasó el gate y se commiteó el 2026-08-28, y **no tenía fila en `MASTER_PLAN.md` ni entrada en `CHANGELOG.md`** — se descubrió el 2026-08-31 sólo porque alguien fue a buscar la fila. `MASTER_PLAN.md` es la fuente de verdad de qué sigue, así que una fila que falta no es un descuido de documentación: es trabajo que el próximo en llegar puede volver a hacer, o dar por hecho lo que no está. Es más fácil que pase al final de una jornada larga y cuando el commit ya está verde, que es cuando se siente terminado. **Al cerrar una fila, el commit y su fila van juntos**; y al retomar, `grep` del último `LV-N` del `git log` en `MASTER_PLAN.md` cuesta un segundo y es la prueba de que el registro llegó.

**Un pendiente anotado en un test es una hipótesis, no un diagnóstico.** El comentario final de `test_lv186_...py` decía que un documento vigente salía del panel con `expirations == []`. Al ir a comprobarlo el 2026-08-31, el ítem **sí** estaba en el contexto: lo que no llegaba era al HTML, por un guard de plantilla (`LV-187`), y al verificar *eso* apareció un defecto más ancho que llega al cálculo de cumplimiento (`LV-188`). Anotarlo estuvo bien —no se perdió—, pero **la nota describía el síntoma con el nombre de una causa supuesta**, y esa causa era falsa: buscarla en `document_subjects` habría sido tiempo perdido. Al dejar un pendiente así, escribir qué se observó y qué **no** se comprobó todavía.

**El paso de despliegue es el de TODO lo que falta en la VM, no el del último commit.** Pasó el 2026-08-31 y tiró producción: `d09a758` traía `registry.0041` (agrega una columna que el panel consulta en cada carga) y `d20057d`, la tanda siguiente, no traía migración propia — así que se entregó "sólo `collectstatic`". Se desplegó eso sobre una VM que no había corrido el `migrate` anterior, y toda página que arma el panel murió con `no such column: registry_costcenter.operates_flights`. **Antes de dictar los comandos, comparar `git log --oneline -1` de la VM con lo que se va a subir y unir los pasos de todas las filas que hay en medio.** Una advertencia al final del mensaje no cuenta: si la tanda necesita `migrate`, el comando va en el bloque, no en una nota.

**Y `showmigrations` es el diagnóstico de treinta segundos** cuando producción devuelve 500 después de un despliegue: `uv run python manage.py showmigrations <app> | tail -6`. Una migración sin `[X]` con código nuevo que ya la usa explica el 500 sin leer un solo traceback.

**`compilemessages` va con `--ignore .claude --locale es`, o no compila el del proyecto.** Sin eso recorre los `.venv` de los worktrees de `.claude/worktrees/` —cada uno con los cientos de `.po` de Django— y el `.mo` del proyecto puede quedarse sin recompilar mientras la salida se llena de "already compiled and up to date". Se detecta con un test que espera la traducción nueva y recibe el texto en inglés. **El `.mo` está versionado**, así que se compila acá y se commitea: el despliegue **no** necesita `compilemessages`.

**Traducción nueva: escribirla a mano en el `.po`, no con `makemessages`.** La regla ya estaba implícita en los siete fuzzy peligrosos que este repo lleva contados; queda explícita: `makemessages` propone traducciones por parecido y una entrada `#, fuzzy` aceptada sin mirar puso en pantalla lo contrario de lo que decía el código (`LV-183`). Escribir el `msgid`/`msgstr` a mano cuesta un minuto y no adivina.

**`{% translate %}` NO traduce un literal que contiene `%(algo)s`.** Devuelve el inglés, mientras `gettext()` con la **misma** cadena devuelve el español — comprobado en aislamiento con `Template(...).render()` contra `gettext()` lado a lado. Se descubrió con un rótulo que el JS necesita con su marcador para poner un número (`LV-198`). Cuando la cadena tiene que llevar un `%(...)s`, traducirla **en la vista** y pasarla por contexto; el tag sirve para todo lo demás.

**Antes de agregar un método a una clase larga, listar los que ya tiene.** Pasó **dos veces el mismo día**: se insertó un `get_context_data` en `FlightPermissionList` y un `save` en `DocumentForm`, y las dos clases ya tenían uno más abajo — Python se queda con la última definición, así que el método nuevo **no se ejecuta y no hay error ninguno**. El síntoma es una clave que no llega al contexto o un campo que se guarda vacío, y se busca en el lugar equivocado. Un `Select-String "^    def "` sobre el rango de la clase cuesta un segundo.

**Chequeos previos a una migración: `values_list`, nunca `.all()`.** Corren con el código nuevo sobre la base vieja, así que un `SELECT *` intenta leer columnas que la migración todavía no creó y falla antes de comprobar nada.

**Un ratio de contraste se calcula, no se lee de un navegador.** Es aritmética sobre dos colores y el CSS los tiene, así que leerlo del navegador añade una fuente de error sin añadir información. `LV-207` traía registrado que 5 de 7 colores del menú no llegaban a 3:1 (`registry 2.41`), y calculados dan **5.91**: los números originales se habían medido contra el fondo equivocado, y estuvieron a punto de provocar el "arreglo" de colores que cumplían de sobra. Al re-medir apareció además que **el navegador integrado devuelve valores que no se corresponden con el CSS para `#sidebar`** — un `background:#ffffff !important` inline no cambia el valor computado, que es imposible en CSS. Un `div` de control sí computó bien, así que el problema es de elementos concretos y no del entorno entero: las lecturas sobre elementos creados al vuelo siguen sirviendo.

**Un número correcto puede describir sólo la mitad de un defecto visual: medir y además mirar.** En `LV-222` la rejilla nueva dejó los `top` de todas las casillas de una fila coincidiendo al milímetro —medido con `getBoundingClientRect`— y la lista **seguía torcida en pantalla**, porque el `float` de `.form-check` hacía caer las etiquetas largas por debajo de la casilla. La medición contestaba la pregunta que se le hizo, no la que importaba. Cuando el pedido es "que se vea prolijo", una captura después de medir cuesta un minuto y es lo que cierra la fila.

**Una custom property se resuelve en el elemento donde se usa, así que escribirla inline puede anular una regla de estado.** En `LV-208`, poner el ancho elegido por el usuario inline en `.sidebar` habría ganado por especificidad sobre `.sidebar.is-collapsed { --ac-sidebar-width: 72px }` y **el botón de colapsar habría dejado de funcionar** en cuanto alguien tocara el borde una vez. El patrón: token aparte para el valor del usuario (`--ac-sidebar-width-user`), escrito en `documentElement`, y el token de layout leyéndolo con fallback.

**`localStorage` lanza —no devuelve `null`— en una ventana privada o con el almacenamiento de sitio bloqueado.** Todo acceso va envuelto, lectura incluida. En `app.js` dos de cuatro accesos no lo estaban mientras los otros dos sí, que es cómo sobrevive este defecto: el patrón correcto estaba a la vista unas líneas más abajo. Y no deja "una preferencia sin recordar": **corta la función a medio camino** — el menú colapsado con su botón rotulado al revés.

**Agregar un campo al `Meta.fields` de un formulario obliga a agregarlo a la plantilla.** Varias plantillas de este repo dibujan campo por campo (`{{ form.x|as_crispy_field }}`) en vez de recorrer el formulario, así que un campo declarado y no dibujado llega vacío en cada POST y **se guarda vacío**. Es `LV-211`, que borraba cinco campos al editar un centro de costo, y se repitió como riesgo en `LV-224` con el motivo de excepción del plazo — un campo cuyo contenido se pierde justo cuando alguien se tomó el trabajo de escribirlo. Al sumar un campo, buscar la plantilla y comprobar si lista campos; si lo hace, sumarlo ahí y dejar un test de que está.

**Los sembrados son idempotentes *por nombre*, así que renombrar una regla sembrada crea otra y deja la vieja viva.** `seed_alert_rules` usa `get_or_create(name=...)` y `seed_document_types` usa `code`. En `LV-226` la tentación era renombrar "Permisos de vuelo por vencer" para que la cadena T-45/T-30/T-15 se leyera ordenada: eso habría dejado **cuatro** reglas activas y duplicado los avisos de todos los permisos. Al extender un sembrado, sumar filas alrededor de las que ya están y no tocarles la clave.

**Un test nuevo que sale verde de primera sobre un defecto que acabas de arreglar merece que rompas el arreglo una vez.** Cuatro veces el 2026-09-01 un test pasó por una razón vecina a la que medía: uno por el mixin que corre antes en el MRO, otro por la etiqueta "Vigencia" que la ficha ya dibujaba, otro por la palabra "Región" presente en otro rótulo. La comprobación cuesta un minuto —revertir, correr, restaurar— y es la única forma de saber que el test sirve. Comparar contra el objeto (`Clase.mensaje`, `gettext("literal")`) en vez de contra un texto tecleado a mano evita la mitad de estos casos.

**`render(request, ...)` corre los context processors, así que una página de error no es autónoma por no extender `base.html`.** La pantalla de CSRF (`LV-215`) tenía la plantilla limpia y seguía pidiendo `request.user.has_perm(...)` y una consulta a la base, por el context processor de `compliance`. En el servidor no estalla —`AuthenticationMiddleware` deja un `AnonymousUser`— pero es apoyar la página de error en el orden de los middleware. En una vista de error, `render_to_string` **sin** `request`: no ejecuta ningún context processor.

**Un test cuyo verde depende del día en que se corre falla disfrazado de regresión.** `test_only_assessable_deliverables_count` (`LV-223`) empezó a dar `assert 0 == 2` sin que nadie tocara la función medida: el módulo fija la ventana en agosto de 2026 y el test dejaba que el modelo sellara la fecha con **ahora**, así que pasó el 31 de agosto y cayó el 1 de septiembre. Apareció en la misma corrida que un cambio no relacionado y parecía su consecuencia. Cuando un test falla y **el diff no toca nada de lo que afirma**, mirar la fecha antes que el diff. Al escribir un test con ventana fija, **fijar también la fecha del dato**: la fecha es andamio y hay que declararla. **Y se pueden buscar antes de que fallen solos** (`LV-257`): `scripts/pytest_clockshift.py` corre la suite con el reloj movido (`uv run --with time-machine`, sin sumar dependencia). La primera pasada, el 2026-09-23, encontró cuatro tests que caían **todos los últimos días de mes**, una bomba que estallaba el 2027-02-09 (una fecha fija del módulo más «200 días») y un defecto real: «¿Puedo volar?» evaluaba la habilitación por modelo con el día real aunque recibiera otro. Para fijar «hoy» en un test sin dependencias, `apps.core.testing.pin_today_mid_month`.

**El gate verifica código, nadie verifica el cableado de producción.** Tres funciones con tests verdes no llegaban a nadie porque el grupo destinatario no tenía correos y un trabajo programado nunca se registró. Al terminar una función que notifica, comprobar el camino completo **en producción** (`--dry-run`, `list-timers`), no sólo el test.

**Todo retiro "de pantalla y no de base" lleva su condición de cierre, escrita el mismo día.** El patrón se aplicó al menos seis veces —`LV-78`, `LV-103`, `LV-150`, `LV-155`, `LV-193`, `LV-221`— siempre con buen criterio y siempre como *paso 1*, y **el paso 2 no se decidió ninguna vez**. El saldo son vistas vivas sin puerta, valores retirados que los filtros deben seguir entendiendo, y columnas que nadie sabe si se pueden borrar. La causa no es descuido: cuando alguien vuelve a mirar la columna, ya nadie recuerda de qué dependía. Así que la fila (y el comentario del campo, si lo hay) tiene que decir **qué tiene que ser cierto para ejecutar el paso 2** — ver `max_altitude_ft` en `apps/operations/models.py` como ejemplo del formato. Un paso 1 sin condición de cierre es deuda con intereses.

**Las migraciones NO se squashean por el tiempo del gate: se midió y no pesan.** Esta lección decía lo contrario hasta el 2026-09-23 —*"el gate ya lo pidió, toca el squash"*, porque una corrida marcó 26 min contra un umbral de 25— y `MASTER_PLAN.md` § Migraciones la había retirado el 2026-09-03 sin que esta guía se enterara, así que durante tres semanas las dos fuentes de mayor autoridad se contradijeron. **La medida**: 158 migraciones desde cero tardan **4,3 s** de un gate de ~1560 (0,28 %), y se aplican **una vez por sesión de pruebas**, no por prueba. Lo que alargaba el gate era la suite, y se resolvió con paralelismo: `-n auto` (`pytest-xdist`, `LV-256`) lo bajó a **3 min** en el equipo de desarrollo. La única razón vigente para squashear es la **legibilidad** de `registry` si pasa de 50 archivos, y antes hay que marcar `elidable=True` en las `RunPython` ya consolidadas o el squash no compacta nada. Dos reglas que salen de ahí: **un disparador sólo vale si la causa que supone está medida**, y **al retirar una regla en el tablero, se retira también acá el mismo día**.

**Un test que localiza por clase de presentación puede quedarse verde midiendo otra cosa, y el cambio que lo rompe no es el que lo hace fallar.** `test_lv118` afirmaba `"bg-danger" in content` para comprobar que la alerta vencida se dibuja en rojo. `UX-01` movió `BUCKET_BADGE_CSS` de las clases de Bootstrap a los tokens `sev-*`, así que la fila pasó a `sev-critical` — y el `bg-danger` que el test seguía encontrando era el del **contador de la barra lateral**, rojo mientras haya cualquier alerta sin resolver. Habría pasado igual con toda la bandeja en gris, y el gate quedó verde en las dos tandas. Dos reglas que salen de ahí: **comparar contra el objeto** (`BUCKET_BADGE_CSS["overdue"]`) y no contra un nombre de clase tecleado, y **acotar la búsqueda a la región que se afirma** (`content.split('id="table-body"')[-1]`), porque el armazón de la página comparte vocabulario con las filas. Al retirar o renombrar una clase de presentación, `grep` de esa clase en `apps/*/test*.py` antes de dar por hecho que nadie la miraba.

**Al verificar CSS o JS en el navegador integrado, forzar la revalidación antes de creerle a la medición.** El servidor de desarrollo sirve los estáticos con cache, así que una edición reciente puede no estar ejecutándose aunque el archivo en disco ya esté bien: `fetch(url)` a secas devuelve la copia del navegador —con sus cabeceras viejas incluidas, que es lo que despista— y `transferSize: 0` lo delata. El patrón que funciona es `await fetch(url, {cache: 'reload'})` sobre cada archivo tocado y después navegar. Pasó tres veces en la jornada del 2026-09-02: dos con `app.css`, donde la regla parecía no aplicar, y una con `theme-init.js`, donde la preferencia parecía no persistir. En los tres casos el código estaba bien y la conclusión inicial era falsa. **Y `collectstatic` corrido para una prueba deja `staticfiles/` en el árbol**: no está versionado, pero conviene borrarlo al terminar para que nadie lo confunda con la fuente.

**Un service worker es el único código de este repo que sobrevive a un `git revert`, y por eso no se despliega encendido.** El 2026-09-08 la primera versión de `UX-26` dejó la aplicación en `ERR_FAILED` en producción: el `cache.put` estaba **dentro** del camino de la respuesta y se esperaba antes de devolverla, así que al rechazar —una 206, una redirigida, la cuota— caía al `catch`, no encontraba nada guardado y **relanzaba**; `respondWith` rechazaba y el navegador mostraba un error de red. La red estaba bien: lo que mató la página fue el intento de guardarla. Y el defecto se propagó solo, porque el worker se instala en la primera visita y toma el control (`clients.claim()`) en la **siguiente** navegación — así que la pantalla que lo probó funcionó y la de al lado no.

Tres reglas, y la tercera es la que importa:

1. **Guardar en caché es un efecto secundario y va fuera del camino de la respuesta**: sin `await` que la retenga, colgado de `event.waitUntil`, con su propio `try/catch`. Si guardar falla se pierde la copia sin conexión, que es lo que corresponde perder. `test_keeping_a_copy_can_never_fail_the_response` lo vigila.
2. **`status === 200`, no `response.ok`**: una **206** también es `ok` y `Cache.put` la rechaza. Y una respuesta `redirected` también.
3. ⚠️ **Nada que intercepte navegaciones se despliega habilitado por defecto.** Va detrás de un interruptor (`SERVICE_WORKER_ENABLED`, en `False`), y la ruta `/sw.js` **sigue existiendo apagada** sirviendo un worker que se desinstala solo, borra la caché y recarga las pestañas que estaba rompiendo. Es el único camino por el que se sana un navegador que ya se quedó con uno roto: un `404` no alcanza —desregistra en Chrome, no en todos, y deja la caché puesta— y un `git revert` tampoco, porque el navegador sigue usando el que ya guardó. Se enciende **después** de ejercitarlo como worker registrado de verdad, no con sondas de `caches`/`fetch` desde una página: eso fue lo que se hizo, y es lo que no detectó nada.

**Un test puede compartir el punto ciego del código que prueba, y entonces el verde no dice nada.** El mismo 2026-09-08, «¿Puedo volar?» (`UX-27`) contestaba **Sí** para una persona que el permiso no nombra: la comprobación se quedaba en *"¿la faena tiene algún permiso vigente?"* y nunca miraba `FlightPermission.operators` / `aircraft_fleet` — el padrón que la DGAC autoriza. Los ocho tests de esa comprobación pasaban, porque **la fixture creaba el permiso con el padrón vacío**: el test no ejercitaba el cruce porque el código tampoco, y ninguno de los dos delataba al otro. Lo encontró el usuario usando la pantalla. Al escribir la fixture de un modelo con relaciones, **poblar las que la regla de negocio usa** —aunque el código todavía no las lea— o el test queda midiendo la mitad fácil. Y cuando una comprobación responde sobre una terna, el test tiene que variar **cada** pata por separado.

**Un `colspan` mayor que las columnas reales rompe el ancho de una tabla de ancho fijo.** El truco de `colspan="99"` para «que abarque todo» es inofensivo con reparto automático y **destructivo** en una `.table-normalized`: el navegador crea las columnas que el `colspan` promete y les reparte el sobrante que le tocaba a la columna `col-flex`. Medido el 2026-09-11 en la lista de operadores, buscando un nombre que no existe: «Habilitaciones» pasaba de **424 px a 5**, y el encabezado de 56 px a **280**, con cada letra en su propia línea — lo reportó el usuario con una captura. Cada columna inventada le roba la mitad a la flexible: con `colspan="8"` daba 212, con 99 daba 5. **El `colspan` de la fila vacía es el número exacto de `<col>`**, y como los dos viven en archivos distintos (`*_list.html` y `_*_rows.html`) hay un guardián que los cruza y que descubre solo las listas normalizadas. `worktable.js` le **suma** uno al inyectar la columna de selección; nunca lo reemplaza por un número grande.

## Referencias

- Plan de trabajo y seguimiento por bloques: `MASTER_PLAN.md` (fuente de verdad de qué sigue).
- Auditoría técnica con evidencia: `AUDIT_CLAUDE.md`.
- Arquitectura: `ARCHITECTURE.md`.
- Registro histórico de lo entregado: `BACKLOG.md` y `CHANGELOG.md`.
- Specs de cambios en curso: `openspec/changes/`.
- Puesta en marcha: `README.md` y `scripts/setup.ps1`.
- Documentación de producto: `docs/` (raíz). Notas internas/históricas: `docs/dev/` (no autoritativas).
