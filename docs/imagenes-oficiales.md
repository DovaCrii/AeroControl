# Imágenes oficiales: foto del modelo y banner de SIGO/SIPA

`LV-399`. AeroControl puede mostrar la **foto oficial del fabricante** de cada modelo de aeronave
en su ficha, y la **imagen oficial** de SIGO y SIPA en las tarjetas del panel.

## Qué son y de quién

- La foto es **del fabricante** (por ejemplo DJI) y el banner es **de la DGAC**. Son material de
  terceros: se usan sólo como referencia interna, dentro de la aplicación y con sesión iniciada.
- **No se guardan en el repositorio** (que es público) ni en `static/`. Se guardan en el
  almacenamiento de documentos del servidor (`DOCUMENTS_DIR`, o el bucket privado si se usa S3),
  re-codificadas a WebP y sin metadatos.
- La ficha muestra el crédito bajo la foto («Imagen: DJI»). Sin foto cargada se ve la silueta
  propia de la serie; sin banner, el icono de siempre.

## Cómo cargar la foto de un modelo

1. Abrir la ficha de cualquier aeronave de ese modelo (se necesita el permiso de **editar
   aeronaves**).
2. En el recuadro de datos, «Cargar la imagen oficial del modelo».
3. Subir el archivo (JPEG, PNG o WebP, hasta 5 MB) **o** pegar la dirección `https` de la imagen
   en el sitio del fabricante. Indicar el crédito (por omisión, el fabricante de la aeronave).

La foto queda asociada al **modelo** (sin distinguir mayúsculas ni espacios): todas las aeronaves
de ese modelo en la empresa la muestran. Cargar otra la reemplaza; la anterior queda guardada y la
auditoría registra quién la cargó y desde qué servidor.

## La imagen de SIGO y SIPA viene con la app

`LV-406`. Nadie sube nada: cada enlace oficial de `apps/core/official_links.py` trae la URL de su
imagen característica (`SIGO_IMAGE_URL`: logo DGAC del portal; `SIPA_IMAGE_URL`: cabecera oficial de
SIPA). Un comando las descarga con las reglas de abajo, las guarda en el almacenamiento privado y las
tarjetas del panel las muestran arriba, a todo su ancho. Sin imagen, la tarjeta conserva su icono.

- **Tras desplegar**, una vez: `uv run python manage.py load_official_link_images`. Es idempotente:
  sólo toca los enlaces sin imagen activa. Informa `ok` o `ERROR` por enlace, un fallo no impide el
  otro, y si alguno falló termina con error al final.
- **Si la DGAC cambia la imagen**: actualizar la constante en `official_links.py` y correr el
  comando con `--force` (reemplaza y borra el archivo anterior).
- La lista de servidores permitidos es `OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS` (abajo).

## Reglas de la descarga desde una dirección

El servidor descarga la imagen por cuenta de quien la pide, así que la dirección tiene que:

- ser `https`, en el puerto estándar y sin usuario ni contraseña;
- apuntar a un servidor de la lista permitida, o a un subdominio suyo:
  - fotos de modelo: `OFFICIAL_IMAGE_ALLOWED_HOSTS` (por omisión `dji.com`, `www.dji.com`,
    `enterprise.dji.com`, `dl.djicdn.com`, `www-cdn.djiits.com`);
  - banners: `OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS` (por omisión `dgac.gob.cl`);
- resolver sólo a direcciones públicas (se rechazan redes privadas, locales y reservadas);
- entregar la imagen directamente: una redirección se rechaza y hay que pegar la dirección final.

Además hay un tope de tamaño (`OFFICIAL_IMAGE_MAX_BYTES`, 5 MB) y de tiempo
(`OFFICIAL_IMAGE_TIMEOUT_SECONDS`, 10 s). Las listas se amplían por variable de entorno,
separadas por coma, sin tocar el código.
