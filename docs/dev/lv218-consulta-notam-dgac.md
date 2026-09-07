# LV-218(b) — Consulta a la DGAC por una fuente estructurada de NOTAM

**Estado:** borrador para revisar y enviar. No lo manda AeroControl: lo manda una
persona de J.E.J. a su contraparte en la DGAC.

**Por qué existe este documento.** `LV-218` paso (a) está hecho: la ficha del
permiso ofrece el enlace al IFIS con la consulta ya armada. El paso (b) —cruzar
automáticamente los NOTAM con el sector del permiso— **no depende de nosotros**,
y por eso la fila está bloqueada fuera del código. Lo que falta saber es si
existe una fuente que se pueda consultar sin raspar HTML.

---

## Lo que ya se verificó, para no preguntar lo que ya sabemos

Investigado el 2026-09-01 sobre `aipchile.dgac.gob.cl`:

- **No tiene API ni feed conocido.** Todo son `GET` con respuesta HTML.
- **Cada NOTAM sí trae centro y radio** en su campo `Q)` —`3324S07048W005` son
  33°24'S, 70°48'W y radio 5 NM—, así que **el cruce geométrico contra la
  coordenada del permiso es calculable** con lo que la app ya sabe hacer. El
  dato está; lo que falta es una forma estable de obtenerlo.

**Por eso la pregunta no es "¿se puede?" sino "¿hay una salida estructurada?".**

---

## El riesgo que justifica preguntar en vez de raspar

Un parseo de HTML que falla —porque el sitio cambió, o no respondió— devuelve
"nada". Y "nada" en esta pantalla se lee como **"no hay avisos"**.

Esa es la diferencia entre una molestia técnica y un problema de seguridad
operacional: un vuelo que sale creyendo que no hay NOTAM cuando en realidad la
consulta falló. Por eso el paso (a) entregó **un enlace y no un resultado** — un
enlace no afirma nada, lleva a la fuente oficial y quien decide vuela mirándola.

---

## Texto propuesto

> **Asunto:** Consulta técnica — disponibilidad de NOTAM en formato estructurado
>
> Estimados:
>
> En J.E.J. Ingeniería S.A. operamos aeronaves pilotadas a distancia (RPA) bajo
> autorizaciones DAN 151, y mantenemos un sistema interno de control de
> operaciones aéreas donde registramos permisos, vigencias y evidencia de
> cumplimiento.
>
> Queremos incorporar la revisión de NOTAM al expediente de cada operación, de
> modo que quede registro de que fue consultada antes de cada vuelo. Hoy lo
> hacemos enlazando al IFIS (`aipchile.dgac.gob.cl/notam`), que consultamos
> manualmente.
>
> Para poder hacerlo de forma confiable, consultamos:
>
> 1. **¿Existe una salida estructurada de NOTAM** —API, JSON, XML, AIXM, o un
>    archivo descargable estable (CSV, RSS)— que podamos consultar
>    programáticamente?
> 2. **¿Autorizan la consulta automatizada** del IFIS y, de ser así, con qué
>    frecuencia consideran aceptable? No queremos generar carga sobre un servicio
>    público sin acuerdo previo.
> 3. **¿Existe una contraparte técnica** a la que podamos dirigir consultas de
>    este tipo?
>
> Aclaramos que **no** buscamos reemplazar la consulta oficial: el objetivo es
> registrar que se realizó y advertir al operador cuando un aviso publicado
> coincida geográficamente con el área autorizada de un permiso. La decisión de
> volar sigue apoyándose en la fuente oficial.
>
> Quedamos atentos y agradecemos de antemano.

---

## Qué se hace con cada respuesta

| Respuesta | Qué se implementa |
|---|---|
| **Hay fuente estructurada** | El cruce completo: consulta, intersección geométrica contra el centro y radio del permiso, y el aviso en la ficha y en el expediente. Con degradación explícita: si la consulta falla, la pantalla dice *"no se pudo consultar"* y **nunca** "no hay avisos". |
| **No hay, o no autorizan la consulta automática** | **La revisión de NOTAM como evidencia**, igual que la meteorológica de `R8.2`: alguien mira el IFIS, marca que lo revisó, y eso queda en el expediente con su fecha y su autor. No cruza automático, pero cierra el renglón con una afirmación humana en vez de una máquina que puede leer "no hay avisos" cuando no pudo leer nada. **Esta salida no depende de nadie más y se puede hacer cuando se quiera.** |

⚠️ **Lo que no se hace en ningún caso: raspar el HTML del IFIS.** No es una
cuestión de dificultad —es factible— sino de riesgo asimétrico, y es la misma
razón por la que el paso (a) entregó un enlace: en cumplimiento, un fallo
silencioso que se lee como "todo en orden" es peor que no tener la función.
