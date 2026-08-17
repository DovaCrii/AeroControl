# La bandeja de alertas: cómo está y hacia dónde ordenarla — 2026-08-14

> Pedido del usuario tras el defecto de las alertas duplicadas (`LV-111`): tomar
> la sección Alertas como caso de estudio, investigar cómo mejorar el flujo, y
> proponer mejoras. Nota interna (`docs/dev/`): lo que se decida se captura como
> filas en `MASTER_PLAN.md`.

## 1 · Qué tiene hoy, verificado en el código

Conviene empezar por acá porque el resultado sorprende: contra las prácticas de
referencia del sector, **el ciclo de vida de una alerta en AeroControl está por
encima del promedio**, y lo que falta no es lo que uno esperaría.

| Etapa | Cómo está resuelta |
|---|---|
| Generación | Regla con umbral en días, corrida diaria a las 06:00 |
| Cierre automático al renovar | ✅ `LV-71` — renovar la fecha cierra su alerta **con motivo trazable** ("Vigencia renovada al AAAA-MM-DD"), y usa **la misma ventana** que la generación, así que no puede quedar oscilando entre cerrarse y recrearse |
| Cierre manual | Con **motivo obligatorio** (ISO 10.2), no un simple "visto" |
| Verificación de eficacia | ✅ A los 30 días (`R7.6a`): resolver dejó de ser terminal |
| Reapertura | ✅ "Deshacer", con la tarjeta enlazada volviendo a su etapa |
| Notificación | Digest diario agrupado en vencidos / 7 / 15 / 30 días |
| No repetición | ✅ Desde `LV-111`: lo resuelto no se recrea, salvo valor nuevo |

**Dónde está por delante de las herramientas del rubro**: casi todas ofrecen
*acknowledge* (alguien lo vio). Acá se exige **causa raíz por escrito** y se
vuelve a preguntar a los 30 días si la acción se sostuvo. Eso no es burocracia
de más: es exactamente la evidencia que un auditor pide y que ningún SaaS de
flota genera por vos.

## 2 · Lo que la práctica del sector dice, y qué aplica

De la literatura de alerting (SRE / operaciones), tres reglas se repiten y las
tres tienen traducción directa acá:

**"Si nadie puede actuar sobre una alerta, esa alerta no debería existir."**
Aplica de lleno, y hay evidencia en la propia captura del usuario: la credencial
de `Carlos Peñailillo` se resolvió con el motivo *"Fuera de CC con operación
RPA"* — o sea, **la alerta no era accionable**: la persona ya no está en la
operación. Ver §3.1, que es el hallazgo más importante de este análisis.

**"Cada alerta necesita una severidad que determine su tratamiento."** Hoy todas
pesan igual: una póliza vencida hace 90 días y una que vence en 30 se ven como
dos filas equivalentes. No hace falta un campo nuevo que alguien deba llenar —
la severidad **se deriva** del vencimiento, que ya se conoce.

**"Agrupar para bajar el ruido."** Seis alertas de "Seguros JAC por vencer" son
**un solo trabajo**. Ojo con el precedente: `R6.3` agrupó filas y `LV-68` lo
revirtió porque agrupaba por *fecha* dando por sentado una causa común que no
existía. Agrupar **visualmente por regla** es otra cosa que resolver en bloque, y
sólo lo primero está en discusión.

**Lo que NO aplica**: rutas de escalamiento tipo PagerDuty, severidades P0/P1 con
llamada a las 3 AM, integraciones con localizador. Esto no es un servicio caído:
un seguro vence con semanas de aviso. El digest diario es la cadencia correcta.

## 3 · Hallazgos concretos (verificados en el código, no supuestos)

### 3.1 · Las alertas siguen a registros que ya no operan — `LV-113`

`generate_alerts` filtra los candidatos con `model.objects.filter(is_active=True)`
y **sólo excluye estados terminales en las reglas que vigilan `status`**. Las
reglas de **fecha** —que son casi todas las reales: seguros, credenciales,
habilitaciones— no excluyen nada.

Consecuencia: **una aeronave dada de baja (`retired`) con el seguro vencido sigue
generando y sosteniendo su alerta para siempre**, igual que un operador que ya no
está en un centro de costo con operación RPA.

Es exactamente el defecto que `LV-90` documentó y corrigió… **en la otra mitad**:
su comentario dice que "una regla que vigilara `status` alertaba sobre aeronaves
dadas de baja para siempre", y `Aircraft.TERMINAL_STATUSES = {"retired"}` existe
desde entonces. Pero esa exclusión nunca se aplicó a la rama de fechas, así que
la mitad más usada del motor quedó con el defecto original.

**Es el hallazgo de más valor de este análisis**: no es una mejora de interfaz,
es ruido permanente e inaccionable en la pantalla donde el usuario trabaja.

### 3.2 · La bandeja no tiene orden definido — `LV-112`

`Alert` no declara `ordering` en su `Meta` y `AlertList` tampoco ordena. Hoy las
filas salen en el orden que devuelve la base, que **parece** cronológico por
casualidad. Dos consecuencias:

- **Triage arbitrario**: nada garantiza que lo vencido hace tres meses aparezca
  antes que lo que vence en 30 días.
- **Paginación no fiable**: un `LIMIT/OFFSET` sin `ORDER BY` puede repetir o
  saltarse filas entre páginas. Con 8 alertas no se nota; con 50, sí.

Es lo más barato de arreglar de toda la lista y lo único que además corrige una
incorrección técnica, no sólo de producto.

### 3.3 · Ideas sin defecto detrás (para decidir, no urgentes)

- **Severidad derivada** del vencimiento, ordenando y coloreando en consecuencia.
  Cero datos nuevos.
- **Posponer ("recordarme en 15 días")**: hoy la única salida de la bandeja es
  resolver, así que quien quiere sacar algo de la vista sin cerrarlo **resuelve
  falsamente**, y eso contamina la evidencia ISO 10.2 con motivos inventados.
- **Dueño de la alerta**: hoy el digest va a un grupo y ninguna alerta tiene
  responsable nominal.
- **Agrupación visual por regla** en la lista (ver la advertencia de `LV-68`).

## 4 · Orden propuesto

1. **`LV-113`** (alertas sobre registros retirados) — es ruido inaccionable y
   completa una corrección que quedó a medias.
2. **`LV-112`** (orden de la bandeja) — barato, y arregla la paginación.
3. Severidad derivada, que se apoya en el orden de `LV-112`.
4. Posponer / dueño / agrupación: sólo si el volumen lo pide. Con ~6 alertas
   abiertas, agregarlos ahora sería resolver un problema que todavía no existe.

## 5 · Lo que este análisis recomienda **no** hacer

- **No agregar un campo de severidad editable.** Derivarla del dato que ya
  existe; un campo que alguien debe mantener se desactualiza y miente.
- **No reintroducir el resolver en bloque** (`R6.3` → `LV-68`).
- **No copiar rutas de escalamiento** de herramientas de incidentes: la cadencia
  correcta acá es el digest diario, y ya existe.

## Fuentes

- [incident.io — SRE alerting best practices](https://incident.io/blog/sre-alerting-best-practices)
- [PagerDuty — Understanding alert fatigue](https://www.pagerduty.com/resources/digital-operations/learn/alert-fatigue/)
- [OneUptime — Monitoring and alerting best practices](https://oneuptime.com/blog/post/2026-02-20-monitoring-alerting-best-practices/view)
