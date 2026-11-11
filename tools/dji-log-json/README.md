# dji-log-json

Envoltorio mínimo (LV-429) sobre la crate [`dji-log-parser`](https://crates.io/crates/dji-log-parser)
0.5.7, licencia **MIT**. Lee un registro de vuelo de DJI (`DJIFlightRecord_*.txt`) y escribe en la
salida estándar un JSON `{"version", "details", "frames"}`. AeroControl lo invoca desde
`apps/operations/flightlog/dji.py`.

## Uso

```
dji-log-json <log.txt> [--keychains <cache.json>]
```

- La clave de la API de DJI va **sólo** por la variable de entorno `DJI_API_KEY` (nunca por
  argumento: no queda en el historial ni en `ps`).
- Los errores salen por stderr como JSON `{"error": código, "message": texto}` y el proceso termina
  con código 2. Códigos: `usage`, `read_error`, `unsupported_format`, `missing_api_key`,
  `keychain_error`, `incomplete`.
- Con `--keychains`, las llaves de descifrado se guardan tras el primer pedido y las siguientes
  lecturas del mismo log funcionan **sin red**.

## Qué se envía a DJI

Los logs v13 o posteriores están cifrados y sus llaves se piden a la API de DJI. Sólo viaja el
`KeychainsRequest` (versión, departamento y las llaves cifradas del propio log; verificado en
`src/keychain/api.rs` de la crate). La telemetría, las coordenadas y el resto del archivo no salen
del equipo.

## Compilar para la VM

En Linux o WSL, con la cadena de herramientas de Rust instalada (`rustup`):

```
cd tools/dji-log-json
cargo build --release
```

El binario queda en `target/release/dji-log-json` (el directorio `target/` no se versiona).
Cópielo a la VM, fuera del repositorio, y configure en el entorno del servicio:

```
DJI_LOG_PARSER_BIN=/ruta/al/dji-log-json
DJI_API_KEY=<clave de la API de DJI>
```

Sin `DJI_LOG_PARSER_BIN` la pantalla muestra «el lector de DJI no está instalado» y el resto de la
aplicación funciona igual. Las llaves de cada log se guardan en el almacenamiento privado de
documentos (`flightlog-keychains/<id del documento>.json`), nunca en el repositorio ni en estáticos.
