# Port MIT - etapa 1: geometria con PDFium

Fecha: 2026-09-21. Solo se modifico la geometria PDFium; texto e imagenes
siguen en PyMuPDF.

## Rendimiento: A-06

La caja de cada trazo se acumula mientras se construyen sus puntos. Cuando hay
clip, se compara esa caja con cuatro escalares, sin volver a recorrer los
puntos con `min()` y `max()`. El cache de clips PDFium se conserva.

| cProfile | Antes | Despues |
|---|---:|---:|
| Total `convertir` | 40.8 s | 27.1 s |
| `extraer_trazos` | 18.7 s | 13.1 s |
| `saveas` | 7.0 s | 7.2 s |
| `unir_trazos` | 6.8 s | 1.2 s |
| `get_objects` | 3.1 s | 2.1 s |
| llamadas a `min()` | 443,574 | 353,504 |

El mejor tiempo conservando la semantica de recorte es 27.1 s, por encima del
objetivo de 20 s. No se desactivaron clips: aunque una prueba temporal redujo
el tiempo, podria incorporar lineas que otro PDF recorta.

## Regresion

`python herramientas/comparar.py base nuevo` se ejecuto contra `spike/base_fitz/`.
Los conteos PDFium son identicos a `b5b8b25`; las extensiones son identicas a
la base PyMuPDF. Los tiempos son de la corrida posterior, sin profiler.

| Plano | LWPOLYLINE | CIRCLE | HATCH | MTEXT / IMAGE | Extension | Tiempo |
|---|---:|---:|---:|---:|---|---:|
| A-02 | 10,749 | 135 | 3,131 | MTEXT 255 | `(0.245, 0.242, 23.758, 35.761)` | 2.4 s |
| A-06 | 42,988 | 223 | 7,502 | MTEXT 899 | `(0.232, 0.238, 35.772, 23.765)` | 27.1 s (perfil) |
| B-01 | 1,868 | 70 | 4,769 | IMAGE 1 | `(0.143, 0.140, 16.856, 10.858)` | 1.1 s |

Contra `spike/base_fitz/` se mantienen las diferencias esperadas del port:
A-02 (+11 LWPOLYLINE), A-06 (+31 LWPOLYLINE, +6 HATCH) y B-01
(+17 LWPOLYLINE). CIRCLE, MTEXT/IMAGE y extensiones no cambian.

---

# Corrección del coordinador: el costo de rendimiento era del perfilador

Las cifras de 40.8 s y 27.1 s de arriba se midieron **bajo cProfile**, y
cProfile penaliza desproporcionadamente a PDFium: su camino por ctypes hace
muchísimas más llamadas Python pequeñas que PyMuPDF, y el perfilador cobra
por llamada. No reflejan el tiempo real.

Medición limpia, sin perfilador, mediana de 3 corridas por plano:

| Plano | main (PyMuPDF) | port-pdfium | diferencia |
|---|---:|---:|---:|
| A-01 | 6.54 s | 6.90 s | +5.5% |
| A-02 | 2.17 s | 2.32 s | +6.9% |
| A-06 | 8.35 s | 8.62 s | +3.2% |

El costo real del port es de **3% a 7%**, no del 65%. Las corridas sueltas
que dieron 13.98 s y 18.78 s eran ruido de disco (los planos viven en
Dropbox); por eso la mediana de tres.

Esto significa que la etapa 1b se despachó persiguiendo un fantasma. La
optimización que salió de ella —acumular la caja del trazo en una sola
pasada en vez de cinco— es legítima y se queda, pero no resolvía ninguna
regresión real. Y la decisión de NO desactivar los clips fue la correcta
por razones de fidelidad, no de velocidad: nunca hubo que elegir entre las
dos.

## Fidelidad confirmada (port contra base con fitz)

| Plano | LWPOLYLINE | CIRCLE | HATCH | MTEXT | extensión | longitud |
|---|---|---|---|---|---|---|
| A-02 | 10,738 → 10,749 (+0.10%) | 135 = | 3,131 = | 255 = | idéntica | +0.02% |
| A-06 | 42,957 → 42,988 (+0.07%) | 223 = | 7,496 → 7,502 (+0.08%) | 899 = | idéntica | +0.58% |
| B-01 | 1,851 → 1,868 (+0.92%) | 70 = | 4,769 = | — | idéntica | -0.41% |

Las diferencias vienen de cómo PDFium parte los paths dentro de los Form
XObject. Ninguna supera el 1%.
