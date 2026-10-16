# Fondos de cabecera por módulo

Seis máscaras de trazo propias (no vienen de ningún otro proyecto) para la cabecera de las pantallas
genéricas (`.page-header--module`, ver `static/css/identity.css`, sección F2).

| Archivo | Módulo (`data-nav-group`) | Motivo |
|---|---|---|
| `flight-bg.svg` | Vuelo | ruta con waypoints |
| `compliance-bg.svg` | Cumplimiento | sello de líneas finas |
| `reports-bg.svg` | Informes | ejes y barras |
| `maintenance-bg.svg` | Mantenimiento | despiece de tornillería |
| `registry-bg.svg` | Padrón | renglones de ficha |
| `inventory-bg.svg` | Inventario | retícula isométrica de cajas |

Se usan como `mask-image`: sólo cuenta la forma (alfa); el color lo pone el CSS con `--ac-text-secondary`,
así que siguen el tema claro y oscuro. Reglas (las vigila `apps/core/test_lv324_module_header.py`): ≤ 6 KB cada
una, sin `<script`, `href`, `<image>`, `<foreignObject` ni `url(http`.
