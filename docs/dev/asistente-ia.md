# Asistente de consulta con IA — prototipo (`LV-305`)

**Estado:** prototipo, **apagado por omisión** y **sólo en el demo**. No está en producción ni puede
estarlo sin una decisión aparte (ver «Por qué sólo demo»).

## Qué hace

Una pantalla (`/assistant/`) donde se escribe una pregunta («¿qué faenas no tienen permiso
vigente?») y el asistente contesta con **datos agregados de permisos**. No tiene entrada en el
menú: hay que escribir la dirección, a propósito, mientras sea prototipo.

El modelo **no toca la base de datos**. Sólo puede pedir tres herramientas de **solo lectura**
(`apps/assistant/tools.py`), que reutilizan los mismos cálculos que el panel:

| Herramienta | Qué devuelve |
|---|---|
| `permits_summary` | cuántos permisos vigentes, sin empezar, esperando a la DGAC, por vencer y atrasados |
| `cost_centres_permit_status` | por faena: vigentes, esperando, por vencer, próximo vencimiento |
| `expiring_permits` | permisos aprobados que vencen en los próximos N días (folio, faena, fecha) |

## Reglas que no se aflojan

- **Solo lectura.** Ninguna herramienta escribe. Sumar una que escriba (aprobar, crear, editar) es
  una decisión explícita del usuario: una máquina que aprueba o declara cumplimiento es lo contrario
  de la evidencia que piden las normas.
- **Nada personal hacia afuera.** Ni nombres de operadores, ni RUT, ni correos ni teléfonos. Sólo
  folios internos, códigos de faena y fechas. Lo vigila una prueba.
- **El permiso del usuario manda.** Cada herramienta declara el permiso que exige y se comprueba
  contra quien pregunta antes de ejecutarla; la IA no amplía lo que esa persona puede ver.
- **No se guarda la pregunta ni la respuesta.** Se registra quién preguntó, qué herramientas se
  usaron y cuánto tardó, nunca el texto (una pregunta puede nombrar a alguien).
- **Tope de vueltas** (4) y de tamaño de respuesta; si el servicio falla, la pantalla dice «no está
  disponible» sin detalles técnicos.
- **La llave nunca se registra ni se muestra.** Vive sólo en el entorno.

## Por qué sólo demo

El acceso gratuito de NVIDIA (Developer Program) es **sólo para prototipos, investigación y
pruebas**. Atender a usuarios reales es «producción» y exige licencia (NVIDIA AI Enterprise) o
alojar el modelo en infraestructura propia. Por eso la pantalla exige `AI_ASSISTANT_ENABLED` **y**
`DEBUG`: en producción no se enciende aunque alguien ponga la variable. Pasar a producción es una
decisión (y una licencia), no un interruptor. Además, el límite gratuito ronda las 40 solicitudes por
minuto y no hay una política clara de retención de lo que se envía.

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
- La herramienta `cost_centres_permit_status` tiene el mismo alcance que el panel, que no se acota por
  tenant; `expiring_permits` sí.

## Aplicaciones que vale la pena evaluar después (sin hacer)

1. **Leer más del PDF de la DGAC** (tabla de operadores y áreas) para cruzarla con el permiso:
   propone, nunca escribe (el mismo criterio que el folio y la vigencia).
2. **Borrador de la narrativa del informe mensual**, que hoy se escribe a mano. Siempre lo aprueba una
   persona.
3. **Resumen de la bandeja de alertas** («esto es lo urgente de hoy»).
4. **Sugerir el tipo de documento** al subir un archivo.

Cualquiera de ellas manda datos personales (los PDF traen RUT, nombres y teléfonos), así que antes de
construirla hay que decidir qué se anonimiza, y eso depende de **dónde corre el modelo**.
