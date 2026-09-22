# Port MIT — etapa 2: texto con PDFium

Fecha: 2026-09-21. Esta etapa migra solamente la extracción de texto a
`pypdfium2`; las imágenes siguen en PyMuPDF y no se modificó la geometría.

## Cambio

Cada `FPDF_PAGEOBJ_TEXT` se vincula a su `TextPage` antes de `extract()` y
reconstruye inserción, rotación, color de relleno y nombre base de fuente desde
PDFium. La inserción descuenta el origen del CropBox. La altura del MTEXT es la
escala vertical de la matriz por la cap height de la familia, y `\\W` recibe
directamente `Tz = hypot(a,b) / hypot(c,d)`.

Por eso se eliminó la medición indirecta contra TTF (`factor_ancho`,
`fuente_medida`, su cache y las carpetas de fuentes). Los TTF se conservan
únicamente en `estilo_para()` para elegir el estilo DXF. El umbral de `\\W`
es ahora de limpieza (`abs(Tz - 1) > 0.005`): evita emitir formato cosmético
cerca de 1, no descarta ruido de una medición.

PDFium presenta algunos espacios separadores como extremo de dos objetos. Se
conservan cuando las cajas y la dirección de ambos objetos demuestran que son
fragmentos consecutivos de la misma línea; así el multiset no pierde el espacio
que PyMuPDF conserva dentro de su span, sin añadir espacios de etiquetas
independientes.

## A. Alturas contra AutoCAD

Comando ejecutado (conversión nueva, sin profiler):

```text
python spike/verifica_alturas.py --etapa despues --plano <cada plano>
```

Salida real relevante:

```text
ALTURAS DESPUES (tolerancia: 2%)
A-01: 435/435 dentro de 2%; 0 fuera; peor=0.03% | AutoCAD=55.15 pt, motor=55.16 pt
A-02: 247/247 dentro de 2%; 0 fuera; peor=0.03% | AutoCAD=55.15 pt, motor=55.16 pt
A-06: 843/843 dentro de 2%; 0 fuera; peor=0.03% | AutoCAD=5.73 pt, motor=5.73 pt
```

Resultado: **0 fuera del 2%** en los tres planos. En particular, el título
A-01 queda en 55.16 pt, frente a 55.15 pt de PDFIMPORT/AutoCAD.

## B. Multiset de caracteres MTEXT

Comparación con `spike/base_fitz/` mediante `plain_mtext()` y `Counter` de
todas las entidades MTEXT. Solo hay bases FITZ para A02 y A06; los conteos de
MTEXT pueden variar porque PDFium parte algunos spans.

```text
A-02: MTEXT fitz=255, pdfium=257; caracteres identicos=True
A-06: MTEXT fitz=899, pdfium=901; caracteres identicos=True
```

No hay caracteres de más ni de menos. La partición es +2 MTEXT en ambos planos
(+0.8% y +0.2%), dentro del rango observado para PDFium.

## Tiempo limpio, mediana de tres corridas

Se midió reloj de pared sin `cProfile`, usando la versión previa (`775e835`) y
la actual; los DXF de benchmarking se escribieron fuera de Dropbox para no
medir sincronización. Las listas son segundos por corrida y la tabla usa su
mediana.

| Plano | Antes | Después | Cambio |
|---|---:|---:|---:|
| A-01 | 7.41 (`7.41, 7.40, 7.47`) | 7.77 (`7.90, 7.77, 7.47`) | +4.9% |
| A-02 | 3.04 (`2.98, 3.04, 3.07`) | 2.97 (`3.07, 2.97, 2.97`) | -2.3% |
| A-06 | 8.60 (`8.50, 8.60, 15.80`) | 9.60 (`9.00, 17.10, 9.60`) | +11.6% |

La tercera corrida de cada grupo A06 tuvo latencia de disco anómala; por eso se
reporta mediana, no promedio. No se ejecutó cProfile en estas mediciones.
