# Spike de licencia: PyMuPDF → pypdfium2

**Veredicto final: no viable** para relicenciar el motor actual a MIT sin una
pérdida funcional crítica: pypdfium2/PDFium no entrega la secuencia de clips ni
el orden de pintado que hoy usa `get_drawings(extended=True)`.

El sondeo no escribió ni exportó contenido de los planos. Se ejecutó con
`pypdfium2 5.5.0` (licencia `Apache-2.0 OR BSD-3-Clause`), PyMuPDF instalado y
`C:\Windows\Fonts\arial.ttf` sólo como fuente local de prueba de métricas.

| Punto | Estado | Evidencia / sustitución exacta |
|---|---|---|
| 1. Contornos, estilo, orden, fill rule y clips | **BLOQUEADO** | `PdfPage.get_objects(max_depth=15)`, `FPDFPath_CountSegments`, `FPDFPathSegment_GetType/GetClose/GetPoint`, `FPDFPageObj_GetStrokeColor/GetFillColor/GetStrokeWidth` y `FPDFPath_GetDrawMode` cubren geometría, cierre, RGBA, grosor y `FPDF_FILLMODE_ALTERNATE/WINDING`. Pero el recorrido es de objetos/XObjects, no un stream global de pintura; `FPDFPageObj_GetClipPath` devuelve el clip efectivo por objeto, no entradas `clip` con `level` ni una pila/orden. Los clips se replican masivamente por objeto (ver conteos), por lo que no puede alimentar sin rediseño el motor de máscaras actual. |
| 2. Texto (texto, fuente, tamaño, color, bbox, dirección) | **PARCIAL** | `page.get_textpage()`, `PdfTextPage.get_textobj(i)`, `PdfTextObj.extract/get_font/get_font_size`, `PdfObject.get_bounds/get_matrix` y `FPDFPageObj_GetFillColor` dan los campos. PDFium expone objetos de texto/caracteres, no los `lines/spans` ya agrupados de PyMuPDF: hay que reconstruir líneas y spans, y los conteos no coinciden exactamente. |
| 3. Compresión horizontal (`Tz`) | **PARCIAL** | `PdfObject.get_matrix()` contiene la matriz efectiva (incluida la escala visible), y el avance real se puede inferir de bbox/dirección frente a métricas. No hay llamada PDFium que devuelva el operando `Tz` separado; el factor queda confundido con tamaño/fuente/transformaciones y requiere la inferencia que hoy ya hace el motor. |
| 4. Métricas `fitz.Font.text_length` | **CUBIERTO** | `fontTools.ttLib.TTFont(font)["head"].unitsPerEm`, `getBestCmap()` y `font["hmtx"].metrics` calculan `sum(advance) * size_pt / unitsPerEm`. Para producción conviene añadir shaping/kerning OpenType si aparece texto complejo; para los textos simples del sondeo es sustituto directo de avance nominal. |
| 5. Raster a PNG | **PARCIAL** | La ruta disponible es `PdfImage.get_bitmap().to_pil().save(dest, format="PNG")` (o `PdfImage.extract`). Los dos planos probados contenían cero objetos raster, así que la llamada existe pero no se validó contra una imagen real. |
| 6. Tamaño de hoja | **CUBIERTO** | `PdfPage.get_size()` devolvió ancho y alto en puntos. |

## Conteos y tiempo de extracción

Los `contornos_raw` de PyMuPDF excluyen sus entradas `type="clip"`. En PDFium,
`paths` son objetos `FPDF_PAGEOBJ_PATH` tras descender en Form XObjects; son la
aproximación comparable, no una afirmación de que ambos modelos preserven el
mismo orden de pintura. Los tiempos miden abrir y extraer/categorizar la primera
página; no incluyen DXF ni operaciones del motor.

| Plano | Backend | Contornos / paths | Entradas clip | Spans / objetos texto | Segundos |
|---|---:|---:|---:|---:|---:|
| A-02 | PyMuPDF | 29,254 | 2 | 256 | 0.585 |
| A-02 | PDFium | 29,270 | no disponible como entradas; 29,528 clips efectivos por objeto | 257 | 0.950 |
| A-06 | PyMuPDF | 113,296 | 14 | 903 | 2.255 |
| A-06 | PDFium | 113,306 | no disponible como entradas; 114,208 clips efectivos por objeto | 901 | 3.429 |

El API de PDFium sí devolvió 25,158 paths/276,738 segmentos de clip efectivos
en A02 y 44,398/563,934 en A06, reiterados por objetos. Eso confirma que hay
geometría de recorte consultable, pero no el evento de apertura/cierre ni el
nivel que requiere la pila actual; intentar deduplicarlo por puntero tampoco
sirve porque PDFium devolvió un handle distinto para cada objeto.

## Salida literal de la sonda PDFium

```text
PDFium: referencias/A-02.pdf
1 pagina.rect: CUBIERTO  PdfPage.get_size() = 1728.24 x 2592.24 pt
2 paths: 29270; segmentos m/l/c=29676/57160/0; cerrados=3228
  color trazo=29270, color relleno=29270, grosor=26448; fill none/even-odd/nonzero=26448/2665/157
  clips efectivos en objetos=29528; handles unicos=29528; paths/segmentos de clip=25158/276738
  FPDFPageObj_GetClipPath da el clip efectivo por objeto, no entradas clip ni pila/orden de content stream.
3 texto: objetos/spans aproximados=257; chars=2836
  muestra metadata: fuente=MHPWIK+ArialMT tam=1.00 bbox=(265.6, -182.33, 275.0, -176.32) dir=(8.0042, 0.0) color=(128, 0, 255, 255) matriz=(8.0042, 0.0, 0.0, 8.0042, 265.1995, -182.2398)
4 fontTools ancho natural muestra: 1.2783203125 pt
  Tz: matriz del objeto disponible con PdfObject.get_matrix(), pero PDFium no expone Tz separado.
5 imagenes: 0; bitmap->Pillow PNG en memoria=0 (PdfImage.get_bitmap().to_pil().save)
6 tiempo solo abrir+extraer: 0.950 s

PDFium: referencias/A-06.pdf
1 pagina.rect: CUBIERTO  PdfPage.get_size() = 2592.24 x 1728.24 pt
2 paths: 113306; segmentos m/l/c=115030/197722/0; cerrados=7686
  color trazo=113306, color relleno=113306, grosor=107344; fill none/even-odd/nonzero=107344/5356/606
  clips efectivos en objetos=114208; handles unicos=114208; paths/segmentos de clip=44398/563934
  FPDFPageObj_GetClipPath da el clip efectivo por objeto, no entradas clip ni pila/orden de content stream.
3 texto: objetos/spans aproximados=901; chars=8820
  muestra metadata: fuente=HRSMQE+ArialNarrow tam=1.00 bbox=(827.99, -703.81, 832.36, -701.61) dir=(0.0, 5.4061) color=(0, 0, 0, 255) matriz=(0.0, 5.4061, -6.0067, 0.0, 832.3619, -703.862)
4 fontTools ancho natural muestra: 0.55615234375 pt
  Tz: matriz del objeto disponible con PdfObject.get_matrix(), pero PDFium no expone Tz separado.
5 imagenes: 0; bitmap->Pillow PNG en memoria=0 (PdfImage.get_bitmap().to_pil().save)
6 tiempo solo abrir+extraer: 3.429 s
```

La línea base PyMuPDF fue: A02 `contornos_raw=29254 clips=2 spans=256
tiempo_s=0.585`; A06 `contornos_raw=113296 clips=14 spans=903 tiempo_s=2.255`.

## Estimación si se acepta rediseñar clips

Un port de prueba del lector y adaptador de objetos tomaría aproximadamente
**3–5 semanas de ingeniería**: 1 semana de adaptador de paths/estilos, 1–1.5 de
agrupación de texto/métricas/imágenes y 1–2.5 de nuevo algoritmo de recorte,
validación visual y regresión de los DXF. No es un reemplazo mecánico de `fitz`;
la parte de clips debe definirse y aceptarse como rediseño antes de prometer
equivalencia de planos.

## Estado de git

`spike/` quedó como directorio nuevo no rastreado: `git check-ignore -v` no
devolvió regla para las dos sondas ni este informe. No se modificó `.gitignore`,
no se hizo commit y no se generaron/copiarion archivos de los planos.

---

# Addendum (coordinador) — correcciones al veredicto

## Punto 5, raster: CUBIERTO (ya verificado)

Probado sobre `referencias/B-01.pdf`, que sí trae un JPEG
embebido. Sonda: `spike/sonda_imagen.py`. Los tres datos que el motor
necesita salen idénticos:

| Dato que usa el motor | PyMuPDF | pypdfium2 |
|---|---|---|
| Tamaño en píxeles | 97 x 222 | 97 x 222 (`FPDFImageObj_GetImagePixelSize`) |
| Caja en puntos, origen arriba-izq | 1084.68, 592.68, 1191.06, 639.18 | idéntica, vía `get_bounds()` + altura de hoja |
| Píxeles a PNG | `fitz.Pixmap(doc, xref).save()` | `obj.get_bitmap(render=False).to_pil().save()` |

Los PNG difieren en 8,646 de 21,534 píxeles, pero con desviación máxima de
33/255 y media de 0.82: es la diferencia entre dos decodificadores JPEG
(la fuente es DCTDecode), no pérdida de información. Verificado también a
ojo: la misma imagen.

De regalo, `get_metadata()` da bpp, colorspace y DPI, y `get_matrix()`
revela que esta imagen está **rotada 90°** (a=0, b=46.5, c=-106.38, d=0).
El motor actual la coloca alineada a los ejes con `add_image(insert, size)`
e ignora esa rotación — limitación que ya existe hoy con PyMuPDF, no una
regresión del port. pypdfium2 daría de hecho lo necesario para arreglarla.

## Punto 1, clips: no está BLOQUEADO

La pila con `level` no es el objetivo, es el medio. En `pdf2dxf.py:354-373`
esa pila colapsa a **una sola caja por trazo**, `recorte[0]`. El clip
efectivo por objeto que da `FPDFPageObj_GetClipPath` es exactamente ese
resultado, ya resuelto: menos trabajo, no más.

Lo real del hallazgo es coste, no capacidad: PDFium repite la geometría del
clip por objeto (276,738 segmentos en A02) con handle distinto cada vez.
Se resuelve cacheando por firma barata (nº de segmentos + bbox), no
rediseñando el recorte.

## Punto 3, Tz: CUBIERTO, no PARCIAL

El motor **no lee Tz de PyMuPDF**. `factor_ancho()` lo infiere comparando
el ancho del bbox del span contra el ancho natural de la fuente. Ese camino
queda igual con pypdfium2 + fontTools.

## Veredicto revisado

**MIT viable.** El único trabajo de fondo es reconstruir el agrupado de
texto en líneas/spans y la dirección de línea para texto rotado, porque
PDFium entrega objetos de texto y caracteres sin agrupar. Con eso más el
caché de clips: **1-2 semanas**, no 3-5.

---

# Addendum 2 — el adaptador de texto, construido y medido

`spike/adaptador_texto.py` reconstruye desde PDFium los 7 campos que
`extraer_texto()` consume, y los compara span a span contra fitz.
`spike/chequeo_tz.py` audita la compresión horizontal.

## Resultado

| Plano | spans fitz / pdfium | ins | tam_pt | rot | color | fuente |
|---|---|---|---|---|---|---|
| A-02 | 255 / 257 | 0% | 0% | 0% | 0% | 0% |
| A-06 | 899 / 901 | 0% | 0% | 0% | 0% | 0% |
| A-03 | 394 / 395 | 0% | 0% | 0% | 0% | 0% |

Cero diferencias en los cinco campos, sobre 1,480 spans. No se pierde texto:
el multiset de caracteres es idéntico (A03 2,550 = 2,550; A06 6,655 = 6,655);
PDFium sólo parte algunos spans donde fitz los une (2-12% según el plano),
y cada trozo se vuelve su propio MTEXT.

## Los tres errores que hubo que resolver

1. **Origen de coordenadas.** PDFium devuelve el espacio de usuario crudo;
   PyMuPDF normaliza al CropBox. En estos planos el MediaBox está centrado
   en el origen, `(-864.12, -1296.12)-(864.12, 1296.12)`, así que sin restar
   esa esquina todo el texto cae fuera de la hoja y con el signo cambiado.
   Una resta.
2. **Tamaño de fuente.** `get_font_size()` devuelve 1.0: la escala vive en
   la matriz, y hay **dos**. La vertical `hypot(c,d)` es el cuerpo, la
   horizontal `hypot(a,b)` lleva además la compresión. PyMuPDF define el
   tamaño como la media geométrica, `sqrt(|ad-bc|)`: para el título A-02
   da 48.73 pt donde la horizontal sola daba 30.82 y la vertical 77.04.
3. **`extract()` falla** en objetos obtenidos con `get_objects()`: el
   helper no les ata la textpage. Se arregla con `obj.textpage = tp`.

## Hallazgo: la compresión sale exacta, no inferida

El motor hoy infiere el factor comparando el ancho del bbox contra el ancho
natural de la fuente. PDFium da la verdad directamente en la matriz:
`Tz = hypot(a,b) / hypot(c,d)`. Comparados sobre 253 spans del A02:

- mediana del desacuerdo: **0.0002** — coinciden
- pero **7 spans** se desvían, y son los que importan

| texto | factor por bbox (hoy) | Tz real |
|---|---:|---:|
| A-02 | 0.633 | 0.400 |
| <titulo comprimido> | 0.633 | 0.400 |
| REVISIÓN 01. | 1.059 | 1.000 |
| P, E, A, Z (sueltas) | 0.950 | 0.900 |

Los dos primeros no son un error de medición: `0.633 = sqrt(0.400)`. El
motor mide el ancho natural al tamaño de media geométrica, que ya lleva
dentro media compresión, así que el factor le sale como raíz del real. El
ancho final renderizado queda bien —por eso nadie lo notó— pero la altura
usa 48.73 pt en vez de los 77.04 reales: el texto sale correcto de ancho y
achatado de alto.

`REVISIÓN 01.` es un error puro: el motor lo **estira 6%** por ruido de
bbox cuando el PDF no lo comprime en absoluto.

Con la matriz esto deja de ser inferencia: desaparecen `factor_ancho()`,
`fuente_medida()`, la tabla `CARPETAS_FUENTES` y la dependencia de tener
el TTF instalado para medir. Dos líneas de aritmética sustituyen a las tres.

## Estado revisado del port

| | |
|---|---|
| Hoja, métricas, geometría, raster, clips | resueltos (addendum 1) |
| Texto: 5 campos exactos | **resuelto, medido sobre 1,480 spans** |
| Texto: agrupación en spans | difiere 2-12%, sin pérdida de contenido |
| Compresión Tz | **mejor que hoy**: exacta, y quita 3 funciones |

Estimación revisada: **3-5 días**, no 1-2 semanas. El riesgo que justificaba
atacar el texto primero no se materializó.
