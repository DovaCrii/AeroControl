# Imágenes de `static/img/`

## Logo de J.E.J. Ingeniería

| Archivo | Uso | Origen |
|---|---|---|
| `jej-logo-blue.webp` | Sobre fondos claros (tema claro): cabecera de «Cómo funciona», pie de la tarjeta de acceso | Logo propio de J.E.J. Ingeniería S.A., entregado por la empresa (fondo transparente, 2000×1280) |
| `jej-logo-white.webp` | Sobre fondos oscuros (tema oscuro y el panel azul marino del acceso) | Ídem, versión blanca |
| `jej-logo-blue.png` | Membrete de los informes PDF (`apps/core/branding.py`, `LV-144`) | Ídem; no se toca desde la pantalla |

- Es la marca de la empresa, no material de terceros: no lleva licencia libre y no se reutiliza fuera de AeroControl.
- `LV-398`: los dos `.webp` salen de los originales recortando el margen transparente (por el canal alfa) y
  reduciendo a 640×276, que alcanza para dibujarlos nítidos a 2x hasta 320 px de ancho; WebP calidad 90. Pesan
  menos de 40 KB cada uno (lo vigila `apps/core/test_lv398_start_page.py`).
- En pantalla van en par, uno por tema, con las clases `brand-logo--on-light` / `brand-logo--on-dark`
  (`static/css/imagery.css`), que siguen el `data-theme` de `theme-init.js`. Los dos llevan el mismo `alt`.
- Los logos de los informes HTML/PDF de `reporting/` son otros archivos y no dependen de estos.

Las ilustraciones (`illustrations/`) y las fotos (`photos/`) tienen su propio registro de origen y licencia.
