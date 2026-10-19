# Asistente de consulta con IA — prototipo (`LV-305`)

**Estado:** prototipo, **apagado por omisión**. En producción exige además `AI_ASSISTANT_ALLOW_PRODUCTION`
(ver «Interruptor de producción»); mientras no exista la llave de la licencia, producción no cambia.

## Qué hace

Una pantalla (`/assistant/`) donde se escribe una pregunta («¿qué faenas no tienen permiso
vigente?») y el asistente contesta con **datos agregados de permisos**. No tiene entrada en el
menú: hay que escribir la dirección, a propósito, mientras sea prototipo.

El modelo **no toca la base de datos**. Sólo puede pedir diez herramientas de **solo lectura**
(`apps/assistant/tools.py`), que reutilizan los mismos cálculos que el panel:

| Herramienta | Qué devuelve |
|---|---|
| `permits_summary` | cuántos permisos vigentes, sin empezar, esperando a la DGAC, por vencer y atrasados |
| `cost_centres_permit_status` | por faena: vigentes, esperando, por vencer, próximo vencimiento |
| `expiring_permits` | permisos aprobados que vencen en los próximos N días (folio, faena, fecha) |
| `upcoming_maintenance` | mantenciones abiertas próximas, atrasadas o por definir (matrícula, tipo, estado, fecha) |
| `expiring_company_documents` | documentos de aeronaves y faenas por vencer (tipo del catálogo, matrícula o código de faena, fecha); sin documentos de personas |
| `aircraft_insurance_status` | seguro JAC por aeronave: trámite, vencimiento, días |
| `open_alerts_by_urgency` | sólo conteos de alertas abiertas por urgencia y por tipo de entidad |
| `flight_requests_status` | solicitudes de vuelo por estado y las abiertas (faena, estado, tipo, antigüedad) |
| `fleet_availability` | total, disponibles, porcentaje, meta y conteo por estado |
| `aircraft_readiness` | qué dicen los registros de UNA aeronave (estado, seguro, documentos, permiso de su faena); nunca dice «puede volar» y no revisa personas |

**Salida de las herramientas (`LV-340`).** Todo va envuelto como `{"data": ...}`, con a lo más 25
filas (se recortan antes de serializar, así el JSON nunca queda cortado), claves y tipos de una lista
blanca, códigos saneados (30 caracteres, `[A-Za-z0-9-_.]`) y fechas ISO. **Excluido para siempre:**
campos libres (descripción, notas, quién hizo qué, mensaje de alerta, título de solicitud, nombre de
faena, responsables), filas de operadores, habilitaciones o evaluaciones, y «¿puedo volar?» con una
persona. Las matrículas sí salen (son públicas en el registro DGAC). Las citas viven en
`CITATION_ROUTES` (una ruta por herramienta; sólo `pk` con forma de UUID). El panel se dibuja con el
permiso de AL MENOS una herramienta; la pantalla completa conserva `view_flightpermission` (`LV-268`).

## Reglas que no se aflojan

- **Solo lectura.** Ninguna herramienta escribe. Sumar una que escriba (aprobar, crear, editar) es
  una decisión explícita del usuario: una máquina que aprueba o declara cumplimiento es lo contrario
  de la evidencia que piden las normas.
- **Nada personal hacia afuera.** Ni nombres de operadores, ni RUT, ni correos ni teléfonos. Sólo
  folios internos, códigos de faena y fechas (ni siquiera el nombre de la faena). Lo vigila una
  prueba que cubre todas las herramientas (centinelas sembrados en cada campo libre).
- **Cada herramienta acota por la empresa (tenant) de quien pregunta** (`LV-323`).
- **El permiso del usuario manda.** Cada herramienta declara el permiso que exige y se comprueba
  contra quien pregunta antes de ejecutarla; la IA no amplía lo que esa persona puede ver.
- **No se guarda la pregunta ni la respuesta.** Se registra quién preguntó, qué herramientas se
  usaron y cuánto tardó, nunca el texto (una pregunta puede nombrar a alguien).
- **Tope de vueltas** (4) y de tamaño de respuesta; si el servicio falla, la pantalla dice «no está
  disponible» sin detalles técnicos.
- **La llave nunca se registra ni se muestra.** Vive sólo en el entorno.

## Revisión contra el alcance real de la API (2026-10-13)

Se contrastó el prototipo con lo que NVIDIA publica hoy. **Fuentes secundarias en su mayoría** (foros y
guías de terceros); el texto oficial de los términos es un PDF que no se pudo abrir, así que **hay que leerlo
antes de decidir nada de producción**.

| Hallazgo | Qué significa para el prototipo |
|---|---|
| El servicio hospedado se rige por los **«NVIDIA API Trial Terms of Service»**, pensados para **prueba y evaluación, no producción** (secciones 1.2 y 1.4, según un resumen en el foro de NVIDIA). | Confirma el diseño: sólo demo, y la pantalla no existe sin `DEBUG`. |
| Según ese mismo resumen, **NVIDIA puede usar los prompts y respuestas para mejorar sus productos**. NVIDIA no respondió con claridad en el foro. | Es la razón de fondo de que **nada personal ni dato real viaje**: sólo cifras agregadas y folios internos, y **en el demo, sólo datos de demo**. |
| Según el resumen, **el contenido generado no se puede distribuir**. | **No exportar ni pegar respuestas del asistente en informes** ni en documentos que salgan de la empresa. La pantalla las muestra y no las guarda. |
| El acceso es por **créditos limitados** (1 000 al registrarse; hasta 5 000 con correo empresarial) y ronda las 40 solicitudes por minuto. | Se agregó un **tope por usuario y por hora, contado por llamada al servicio** (una pregunta puede hacer hasta 4; el contador vive en la base, en la tabla `AssistantUsage` (LV-326), compartido por todos los procesos) (`AI_ASSISTANT_MAX_PER_HOUR`, 30) más un **tope global por día** (`AI_ASSISTANT_DAILY_CAP`, 300; 0 = sin tope), ambos revisados antes de cada llamada. Cada pregunta deja una fila con quién, herramientas, llamadas, milisegundos, tokens, modelo y resultado, **nunca** el texto de la pregunta ni de la respuesta; un fallo de red antes de responder devuelve la llamada al tope (un 429 no). El registro es de sólo lectura en el admin para no gastar créditos por accidente, y un mensaje propio cuando el servicio responde que se alcanzó el límite. |
| El modelo por omisión (`meta/llama-3.3-70b-instruct`) existe en el catálogo y su ficha lo describe con «function calling». | Es la herramienta que usa el asistente. **Sigue sin probarse contra el servicio real.** |
| Caminos a producción según NVIDIA: **alojar el modelo en infraestructura propia** o usar la API sin servidor de pago con una licencia NVIDIA AI Enterprise. | Es la decisión que falta si algún día se quiere usar con usuarios reales; cambia también qué datos se pueden enviar. |

## Panel lateral (`LV-332`)

Además de `/assistant/`, en cada pantalla aparece un botón «Ask» (abajo a la derecha; Ctrl+J) que abre un panel
lateral. **Sólo si** `assistant_available()` (encendido y `DEBUG`) **y** la persona tiene `view_flightpermission`:
si no, el servidor no dibuja ni el botón ni el panel (context processor `assistant_panel`). El panel envía la
pregunta por `POST assistant/ask/panel/` (CSRF normal) y recibe el fragmento `_answer.html`.

- **Historial sólo en el DOM:** recargar lo pierde; no se guarda nada en el navegador ni en el servidor.
- **Citas «Cited records»:** las arma el servidor con `reverse()` a partir de lo que devolvieron las herramientas
  (`expiring_permits` incluye `pk`, que no es dato personal), ya acotado por empresa. El texto del modelo sale
  **escapado** y nunca se dibuja una URL escrita por él.
- **Sugerencias por módulo:** el módulo «flight» (permisos) ofrece «¿Qué permisos vencen…?» y «¿Qué faenas no tienen
  permiso vigente?»; el resto, la segunda.
- El interruptor de producción (`AI_ASSISTANT_ALLOW_PRODUCTION`, `LV-336`) vive en `assistant_available()`, un solo punto.

## Interruptor de producción (`LV-336`)

Decisión del usuario (2026-10-19): el asistente **se usará en producción con la licencia de NVIDIA**, que la
persona obtiene y cuya llave pone en el entorno de la VM (nunca en el repositorio ni en el chat). Mientras la
llave no exista, producción no cambia.

`assistant_available()` = `AI_ASSISTANT_ENABLED and (DEBUG or AI_ASSISTANT_ALLOW_PRODUCTION)`.

| Situación | Resultado |
|---|---|
| Desarrollo/demo (`DEBUG`) con `AI_ASSISTANT_ENABLED=1` | Abierto, como antes. |
| Producción con sólo `AI_ASSISTANT_ENABLED=1` | **Cerrado**: 404 y ningún HTML del panel. |
| Producción con `ENABLED=1` y `AI_ASSISTANT_ALLOW_PRODUCTION=1` | Abierto. Sin llave, la pantalla avisa «no configurado». |
| `AI_ASSISTANT_ENABLED=0` (o ausente) | Cerrado siempre. |

`AI_ASSISTANT_ALLOW_PRODUCTION` está **apagado por omisión**. Los permisos no cambian: sigue haciendo falta
`view_flightpermission` y rige el contrato de `LV-268`; no hay roles nuevos.

**Apagado de emergencia:** `AI_ASSISTANT_ENABLED=0` en el entorno de la VM y reiniciar el servicio. La pantalla y
el panel dejan de existir en la siguiente petición del proceso nuevo.

### Puntos de la licencia que hay que confirmar con NVIDIA antes de activar

Nada de esto consta todavía; son preguntas, no afirmaciones. Dejar la respuesta (con fecha y quién la dio) aquí.

1. ¿La licencia que se obtendrá cubre **uso en producción con usuarios internos reales** (personal de la empresa)?
2. ¿NVIDIA **guarda** lo que se envía (preguntas, respuestas, metadatos) y por cuánto tiempo? ¿Lo usa para
   **entrenar o mejorar** sus productos? ¿Se puede desactivar?
3. ¿Se puede **redistribuir o usar lo generado** (por ejemplo en informes que salen de la empresa)? Hasta saberlo
   no se pega ni exporta nada del asistente.
4. **Límites** (solicitudes por minuto, créditos, tokens) y **precio**, para ajustar `AI_ASSISTANT_MAX_PER_HOUR` y
   `AI_ASSISTANT_DAILY_CAP`.
5. ¿El modelo elegido (`NVIDIA_MODEL`) admite llamadas a funciones bajo esa licencia y en qué región se procesa?

### Lista de verificación de activación

1. Confirmar los puntos de arriba con NVIDIA.
2. En la VM (`p340`), poner `NVIDIA_API_KEY` en el archivo de entorno del servicio (nunca en el repo ni en el chat).
3. Poner `AI_ASSISTANT_ENABLED=1` y `AI_ASSISTANT_ALLOW_PRODUCTION=1` en el mismo archivo y ajustar los topes.
4. Reiniciar el servicio. Verificar con `echo` que `DJANGO_SETTINGS_MODULE` y `DB_PATH` son los de producción.
5. `uv run python manage.py assistant_probar`: debe decir `key: present`, `switch: OPEN` y los topes esperados.
6. `uv run python manage.py assistant_probar --ping`: una sola llamada; debe decir `ping: ok` con latencia y tokens.
7. Entrar con una cuenta con `view_flightpermission`, hacer una pregunta y revisar en el admin la fila de
   `AssistantUsage` (quién, herramientas, llamadas, tokens, resultado; nunca el texto).
8. Para apagar: `AI_ASSISTANT_ENABLED=0` y reiniciar.

`assistant_probar` nunca imprime la llave ni el texto del modelo; sin `--ping` no llama al servicio.

## Por qué hay un interruptor aparte

El acceso gratuito de NVIDIA (Developer Program) es **sólo para prototipos, investigación y
pruebas**. Atender a usuarios reales es «producción» y exige licencia (NVIDIA AI Enterprise) o
alojar el modelo en infraestructura propia. Por eso, fuera de `DEBUG`, no basta `AI_ASSISTANT_ENABLED`: hace
falta `AI_ASSISTANT_ALLOW_PRODUCTION`, que sólo se enciende con la licencia resuelta. Además, el límite
gratuito ronda las 40 solicitudes por minuto y no hay una política clara de retención de lo que se envía.

## Cómo probarlo en el demo

En **su propia terminal de PowerShell** (la llave no se pega en el chat ni en ningún archivo del
repositorio), antes de arrancar el demo:

```powershell
$env:AI_ASSISTANT_ENABLED = "1"
$env:NVIDIA_API_KEY = "<su llave de build.nvidia.com>"
./scripts/run-demo.ps1
```

Luego, con sesión iniciada, abrir `http://127.0.0.1:8010/assistant/`. Si falta la llave, la pantalla
lo dice. El modelo por omisión es `meta/llama-3.3-70b-instruct` (`NVIDIA_MODEL` lo cambia); hay que
confirmar en `build.nvidia.com` que el modelo elegido admite llamadas a funciones.

## Qué NO se probó

- **Contra el servicio real.** Las pruebas usan un cliente falso: verifican el ciclo, la seguridad y
  la forma de la petición, pero **no** que NVIDIA responda como se espera, ni la calidad de las
  respuestas, ni que el modelo elegido use bien las herramientas. Eso es lo primero que hay que mirar
  con la llave puesta.
- Todas las herramientas se acotan por empresa, incluida `cost_centres_permit_status` (el panel, que
  llama sin `user`, sigue viendo todo).

## Aplicaciones que vale la pena evaluar después (sin hacer)

1. **Leer más del PDF de la DGAC** (tabla de operadores y áreas) para cruzarla con el permiso:
   propone, nunca escribe (el mismo criterio que el folio y la vigencia).
2. **Borrador de la narrativa del informe mensual**, que hoy se escribe a mano. Siempre lo aprueba una
   persona.
3. **Resumen de la bandeja de alertas** («esto es lo urgente de hoy»).
4. **Sugerir el tipo de documento** al subir un archivo.

Cualquiera de ellas manda datos personales (los PDF traen RUT, nombres y teléfonos), así que antes de
construirla hay que decidir qué se anonimiza, y eso depende de **dónde corre el modelo**.
