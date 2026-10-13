# Fotos de equipos (opcional)

Si dejas aquí una foto de un equipo **con derecho de uso**, la ficha de las aeronaves de esa serie la
muestra en lugar del dibujo.

Nombres admitidos (la **serie** es la primera palabra del modelo, en minúsculas):

| Archivo | Se muestra en las aeronaves cuyo modelo empieza por |
|---|---|
| `mavic.webp` (o `.jpg`, `.jpeg`, `.png`) | Mavic |
| `matrice.webp` | Matrice |
| `phantom.webp` | Phantom |
| `elios.webp` | Elios |
| `generic.webp` | cualquier otra serie |

**Reglas**
- **Sólo fotos que puedas usar**: las de prensa que el fabricante publica para medios, o fotos propias.
  No se copian imágenes de buscadores ni de tiendas: tienen derechos de autor y marca.
- Proporción 4:3, ancho de 600 a 900 px, **menos de 150 KB** (`.webp` pesa menos que `.jpg`).
- En producción hay que correr `collectstatic` después de agregar o cambiar una foto; hasta entonces
  la ficha sigue mostrando el dibujo (no se rompe).
- No hay que tocar código ni migraciones: basta con el archivo.
