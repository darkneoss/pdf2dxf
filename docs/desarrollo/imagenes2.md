# IMAGENES2 — validacion de raster PDFium

Fecha: 2026-09-21.  Se trabajo localmente sobre `imagenes`; los PDF de
`referencias/` no se copiaron ni se enviaron fuera del equipo.  Este archivo es
un registro de pruebas y no forma parte del commit.

## Cambio

`extraer_imagenes()` ya no reduce una imagen a su caja.  Para cada IMAGE toma
la matriz PDFium `(a, b, c, d, e, f)`: el insert DXF es `(e-crop_x0,
f-crop_y0) / 72`, `u_pixel=(a,b)/(72*ancho_px)` y
`v_pixel=(c,d)/(72*alto_px)`.  Por tanto se conserva tanto el giro como las
dos escalas independientes; no se aplica el volteo temporal que se usa en
paths/texto porque la matriz ya esta en coordenadas PDF abajo-izquierda y DXF
tambien.

Antes de escribir PNG se descartan las imagenes cuya media RGB es `>=254`.
Las teselas restantes solo se fusionan si son de la misma resolucion y modo,
son una fila sin giro, tienen el mismo eje vertical y cada costura es contigua
a `<=0.005 in`; se usa el extremo real de la ultima tesela, no un paso nominal.
La envolvente de la imagen compuesta se recalcula y, si no coincide con la
envolvente de sus teselas a esa tolerancia, se dejan las teselas individuales.
`--no-merge-images` y `--sin-unir-imagenes` evitan solo esa fusion.

Los PNG conservan el prefijo saneado del nombre del dibujo.  Al regenerar un
dibujo se limpian exclusivamente sus PNG con sufijo numerico, evitando que un
PNG viejo de esa misma conversion quede huerfano sin tocar los de otros planos.

## B-01 — giro

PDFium informa matriz `(0, 46.5, -106.379997, 0, 1191.060059, 152.820007)`,
imagen `97 x 222 px` y bounds PDF `(1084.680054, 152.820007,
1191.060059, 199.320007)`.  El CropBox es `(0, 0, 1224, 792)` (la
normalizacion se aplica en el insert); la comprobacion del DXF emitio:

```text
images 1
(16.54250081, 2.12250010, 0.0) (0.0, 0.00665808, 0.0) (-0.00665541, 0.0, 0.0) (97.0, 222.0, 0.0)
audit 0
```

Los vectores multiplicados por los pixeles dan `u=(0, 0.64583333)` y
`v=(-1.47749996, 0) in`: la caja DXF resultante es
`(15.06500085, 2.12250010)–(16.54250081, 2.76833343)`, que es exactamente la
caja de la matriz PDFium normalizada al CropBox y dividida entre 72 (redondeo
de coma flotante menor de `7e-7 in`).

## A-03-fachadas — blancos y mosaico

PDFium encontro 375 teselas de `960 x 960 px`.  Se descartaron 134 por media
RGB `>=254`; quedan 241 teselas (incluye las 68 casi blancas, que no se
descartan).  La ejecucion por defecto produjo **16 IMAGE**: cinco tramos de
12, cuatro de 21, tres de 23, tres de 2 y uno de 22 teselas.

Comprobacion independiente de cada IMAGE compuesta contra la envolvente de
las teselas fuente:

```text
0 23 error_in 0.000000636
1 23 error_in 0.000000636
3 23 error_in 0.000000636
5 21 error_in 0.000000212
6 21 error_in 0.000000212
7 21 error_in 0.000000212
8 21 error_in 0.000000212
17 22 error_in 0.000000636
24 12 error_in 0.000000000
25 12 error_in 0.000000212
26 12 error_in 0.000000106
27 12 error_in 0.000000212
28 12 error_in 0.000000212
319 2 error_in 0.000000636
358 2 error_in 0.000000636
359 2 error_in 0.000000636
nonwhite 241 merged 16 worst_in 0.000000636 worst (0, 23)
```

El peor error es `0.000000636 in`, frente al limite de `0.005 in`.  La salida
sin fusion confirma que se conservan las teselas no blancas:

```text
unmerged images 241 defs 241 png 241 audit 0
```

La salida normal confirma que no hay PNG huerfano:

```text
images 16 defs 16 png 16 pairs True audit 0
```

En el lote, donde solo fachadas y B-01 aportan raster, tambien se
comprobo la biyeccion completa:

```text
IMAGE 17 IMAGEDEF 17 PNG 17 all_bijective True
```

## Lote y regresion

Se compararon los conteos `[LWPOLYLINE, CIRCLE, HATCH, MTEXT]` contra `main`;
son iguales en los ocho planos y el Auditor de ezdxf da cero errores en cada
DXF. Salida real de la comparacion:

```text
A-01.dxf main/new [38659, 331, 5016, 447] [38659, 331, 5016, 447] audit 0 0 OK
A-02.dxf main/new [10749, 135, 3131, 257] [10749, 135, 3131, 257] audit 0 0 OK
A-03.dxf main/new [29203, 217, 2893, 395] [29203, 217, 2893, 395] audit 0 0 OK
A-04.dxf main/new [59188, 277, 6927, 1485] [59188, 277, 6927, 1485] audit 0 0 OK
A-04b.dxf main/new [54529, 264, 4541, 337] [54529, 264, 4541, 337] audit 0 0 OK
A-05.dxf main/new [48618, 52, 2905, 753] [48618, 52, 2905, 753] audit 0 0 OK
A-06.dxf main/new [42988, 223, 7502, 901] [42988, 223, 7502, 901] audit 0 0 OK
B-01.dxf main/new [1868, 70, 4769, 0] [1868, 70, 4769, 0] audit 0 0 OK
```

Tres corridas limpias del lote, sin cProfile: `129.1 s`, `106.9 s`, `112.3 s`;
mediana: **112.3 s**. Salida real de la tercera corrida:

```text
A-01.pdf: raw 74223 -> poly 38659, circ 331, hatch 5016, text 447, img 0; TOTAL 44453 in 10.9s
A-02.pdf: raw 29676 -> poly 10749, circ 135, hatch 3131, text 257, img 0; TOTAL 14272 in 4.1s
A-03.pdf: raw 57991 -> poly 29203, circ 217, hatch 2893, text 395, img 16; TOTAL 32724 in 15.6s
A-04.pdf: raw 318520 -> poly 59188, circ 277, hatch 6927, text 1485, img 0; TOTAL 67877 in 36.2s
A-04b.pdf: raw 139887 -> poly 54529, circ 264, hatch 4541, text 337, img 0; TOTAL 59671 in 16.2s
A-05.pdf: raw 90681 -> poly 48618, circ 52, hatch 2905, text 753, img 0; TOTAL 52328 in 12.5s
A-06.pdf: raw 115030 -> poly 42988, circ 223, hatch 7502, text 901, img 0; TOTAL 51614 in 14.6s
B-01.pdf: raw 6734 -> poly 1868, circ 70, hatch 4769, text 0, img 1; TOTAL 6708 in 1.9s
batch done in 112.3s
```
