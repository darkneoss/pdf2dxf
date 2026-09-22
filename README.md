# pdf2dxf

*English · [Español](README.es.md)*

Converts **vector PDF drawings to DXF** without AutoCAD, without licences and
without cloud services. A single Python file.

It was built by comparing its output against AutoCAD's own `PDFIMPORT`, entity
by entity and property by property, until its behaviour was reproduced. On a
44,360-entity reference drawing the entity count differs by **0.2%**, and the
extents, layer colours, text heights and styles match.

On one point it does better: it **honours the horizontal compression of text**,
which AutoCAD discards on import. The factor is read straight from the text
matrix, so it is exact rather than inferred — and no font has to be installed
for it to work, on any platform.

---

## What it does

| PDF element | DXF entity |
|---|---|
| Lines and rectangles | `LWPOLYLINE`, contiguous segments joined |
| Circular polygons | `CIRCLE` |
| Bézier curves | flattened `LWPOLYLINE` |
| Fills | solid `HATCH`, 50% transparency |
| Text | editable `MTEXT`, real font and width |
| Raster images | `IMAGE` + PNG files in a `PDF Images` folder |

Layers created: `PDF_Geometry`, `PDF_Text`, `PDF_Solid Fills`, `PDF_Images` —
the same names AutoCAD uses, so existing workflows keep working.

## What it does not do

- **Scanned PDFs.** If the PDF is an image there is no geometry to extract.
  Zoom in on a line: crisp means vector, pixelated means a scan.
- **DWG.** It is a closed Autodesk format and no open library writes it
  reliably. DXF opens natively in AutoCAD and every other CAD package. With
  `--dwg` the tool uses [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
  if it is installed — free of charge, proprietary, installed separately.
  In the interest of honesty: that path has never been exercised here, because
  the converter was never installed. The DXF path is the tested one.
- **Recover the original project.** A PDF yields geometry, text and fills on
  three layers: no blocks, no project layers, no associative dimensions. If
  whoever issued the drawings still has the DWG or the RVT, asking for it
  saves both the conversion and the cleanup.

---

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python pdf2dxf.py drawing.pdf                  # -> drawing.dxf
python pdf2dxf.py drawing.pdf output.dxf
python pdf2dxf.py folder/ --batch              # -> folder/DXF/
python pdf2dxf.py folder/ --batch --dwg        # plus DWG, if ODA is present
```

### Options

They mirror AutoCAD's *Import PDF* dialog. Spanish aliases in brackets also
work.

| Option | Effect |
|---|---|
| `--no-join` [`--sin-unir`] | Do not join contiguous segments |
| `--no-fills` [`--sin-rellenos`] | Do not import solid fills |
| `--no-images` [`--sin-imagenes`] | Do not import raster images |
| `--no-text` [`--sin-texto`] | Do not import text |
| `--no-masks` [`--sin-mascaras`] | Drop the white fills behind text |
| `--layers=type` [`--capas=tipo`] | `PDF_Geometry` / `PDF_Text` / `PDF_Solid Fills` (default) |
| `--layers=color` [`--capas=color`] | One layer per object colour |
| `--layers=single` [`--capas=una`] | Everything on layer 0 |
| `--arcs` [`--arcos`] | Rebuild arcs (off by default: may invent curves) |
| `--merge-images` [`--unir-imagenes`] | Stitch tiled rasters into fewer images (off by default: see below) |
| `--linetypes` [`--tipos-linea`] | Rebuild dashed lines as one polyline with a linetype (off by default) |
| `--binary` [`--binario`] | Binary DXF: same content, half the size |
| `--batch` [`--lote`] | Convert every PDF in a folder |
| `--dwg` | Also convert to DWG with ODA File Converter |

### A batch, start to finish

Say you have a folder of drawings:

```
proyecto/
    A-02-roof-plan.pdf
    A-06-drainage.pdf
```

```bash
python pdf2dxf.py proyecto/ --batch
```

```
  A-02-roof-plan.pdf
     sheet 24.0 x 36.0 in | raw 29660 -> poly 10738, circ 135, arc 0, hatch 3131, masks dropped 0,
     text 255 (81 width-corrected), img 0
     TOTAL 14259 entities in 6.7s
  A-06-drainage.pdf
     sheet 36.0 x 24.0 in | raw 115012 -> poly 42957, circ 223, arc 0, hatch 7496, masks dropped 0,
     text 899 (143 width-corrected), img 0
     TOTAL 51575 entities in 52.3s

  batch done in 59.1s -> proyecto/DXF
```

```
proyecto/
    A-02-roof-plan.pdf
    A-06-drainage.pdf
    DXF/
        A-02-roof-plan.dxf
        A-06-drainage.dxf
```

Dashed lines arrive as loose fragments, because the exporter flattens the
dash pattern into separate segments — an axis line can be 153 two-point
polylines, and none of these PDFs carries a dash array to read instead.
`--linetypes` groups the fragments that share a line, a colour and a
lineweight, and where the gaps are regular it replaces them with a single
polyline carrying a generated linetype. It removes 12% to 18% of the
entities, and an axis becomes one object you can select, restyle or stretch.
The filter is deliberately strict: it needs four fragments, evenly spaced
gaps and no gap wider than twice the median, so a real break in the drawing
is never bridged. On one drawing it merges 54 of 104 candidate lines and
leaves the rest alone. AutoCAD's own importer does none of this — it creates
no linetypes at all — so there is nothing to compare against; judge it
against the PDF.

Some PDFs slice a shaded elevation into a grid of raster tiles — one drawing
here arrives as 375 of them, 134 of which are blank paper and get dropped.
`--merge-images` stitches the rest into 16, and the DXF it writes is correct:
pixel size, image axes and the placement envelope all agree to within a
millionth of an inch. AutoCAD still refuses to draw the result, reporting a
21,120-pixel-wide raster as 1.6 units instead of 35.2, so the elevation
renders at a thirteenth of its width. The flag is off for that reason, and
kept only for anyone who wants to pick the problem up; the untested guess is
that the 23:1 aspect ratio is what breaks it, not the absolute width.

Reading the output: **raw** is the number of contours found in the PDF and
**poly** how many polylines they were joined into — the gap between the two is
the joining doing its job. A suspiciously low entity count (tens instead of
thousands) means the PDF was probably a scan. Drawings with raster images also
get a `PDF Images` folder next to the DXF, which must travel with it.

### Scale

The drawing arrives in **paper inches**: a 24×36" sheet measures 24 × 36
units, exactly as with `PDFIMPORT`. For real millimetres:

```
factor = 25.4 × scale denominator
1:50 → 1270      1:75 → 1905      1:100 → 2540
```

Scale afterwards, drawing by drawing: plans, sections and details rarely share
a scale. Measure a known dimension with `DIST` before applying `SCALE`.

---

## Verifying changes

`herramientas/comparar.py` reports property differences between two DXF files.
It is a development tool; it is not needed to convert anything.

**Regression** — no AutoCAD required. Convert the same PDF before and after
touching the engine and compare: it shows exactly which properties moved.

```bash
python pdf2dxf.py drawing.pdf before.dxf
# ...changes to the engine...
python pdf2dxf.py drawing.pdf after.dxf
python herramientas/comparar.py before.dxf after.dxf
```

**Fidelity** — only if you have AutoCAD. Import the same PDF with `PDFIMPORT`,
export it with `DXFOUT` and compare against that reference. That is how the
rules below were worked out.

It compares header variables, extents, drawn length, entity types, lineweights,
text heights and styles, hatch properties, layers and colours. Rows marked `<-`
are the ones that differ.

---

How each of those changes was measured, and against what, is in
**[docs/desarrollo/](docs/desarrollo/README.en.md)** — the development log.

The rules of AutoCAD's importer that had to be reverse engineered to get
here are in **[docs/autocad-rules.md](docs/autocad-rules.md)** — useful if
you plan to change the engine.

---

## Licence

**MIT** — see [LICENSE](LICENSE). Use it in commercial or closed-source
work; nothing has to be given back.

Every dependency is permissive, which is what makes that possible:
[pypdfium2](https://pypdfium2.readthedocs.io/) is BSD-3-Clause over Google's
PDFium (Apache-2.0), [ezdxf](https://ezdxf.mozman.at/) is MIT and
[Pillow](https://python-pillow.org/) is MIT-CMU.

Earlier versions were AGPL-3.0, because PDF reading went through PyMuPDF and
that library is AGPL-3.0 or commercial from Artifex. The licence was never a
choice, so the PDF reader was rewritten on PDFium to remove it.
