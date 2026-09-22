# Fuera de hoja — validación

Fecha: 2026-09-22.  Se comparó la caja de cada PageObject de PDFium contra
el `CropBox` (no contra el `MediaBox`); sólo se descarta cuando queda por
completo fuera. Los objetos que cruzan un borde se conservan.

## Sondeo PDFium antes de emitir

```text
Plano                                    PATH fuera  TEXT fuera  IMAGE fuera
A-01                0           0            0
A-02                        0           0            0
A-03                              0           0            0
A-04                0           0            0
A-04b-DETALLES-COMPLEMENTARIOS-Rev.0             0           0            0
A-05                     0          56            0
A-06          0           0            0
B-01                                      0           0            0
```

## MTEXT contra `main`

```text
A-01: main=447, fix=447, delta=0
A-02: main=257, fix=257, delta=0
A-03: main=395, fix=395, delta=0
A-04: main=1485, fix=1485, delta=0
A-04b: main=337, fix=337, delta=0
A-05: main=753, fix=697, delta=-56
A-06: main=901, fix=901, delta=0
B-01: main=0, fix=0, delta=0

A-05 position_new_not_main=0; removed=56;
text_insert_outside_sheet=0; audit_errors=0
```

Los 56 descartados son sólo texto: por ello los conteos LWPOLYLINE, CIRCLE,
HATCH e IMAGE del lote no cambian. Las tres corridas del lote produjeron los
mismos conteos; la última fue auditada completa.

## Lote final + auditor ezdxf

```text
Plano                                    LWPOLYLINE  CIRCLE  HATCH  IMAGE  MTEXT  errores
A-01             38659     331   5016      0    447        0
A-02                     10749     135   3131      0    257        0
A-03                           29203     217   2893    375    395        0
A-04             59188     277   6927      0   1485        0
A-04b-DETALLES-COMPLEMENTARIOS-Rev.0          54529     264   4541      0    337        0
A-05                 48618      52   2905      0    697        0
A-06       42988     223   7502      0    901        0
B-01                                    1868      70   4769      1      0        0
```

## Alturas (`spike/verifica_alturas.py`, emparejado por texto + posición)

```text
A-01: 435/435 dentro de 2%; fuera=0; peor=0.0251%
A-02: 247/247 dentro de 2%; fuera=0; peor=0.0251%
A-06: 843/843 dentro de 2%; fuera=0; peor=0.0251%
```

## Tiempo limpio (sin cProfile)

```text
BATCH 1: 112.847s
BATCH 2: 109.223s
BATCH 3: 121.818s
BATCH_MEDIAN: 112.847s
```
