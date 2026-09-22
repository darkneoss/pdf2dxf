# AutoCAD import rules

How AutoCAD's `PDFIMPORT` behaves, worked out by measuring its own
output. Each rule is also documented at the point of the code that
implements it.

---

These are AutoCAD's import rules, deduced by measuring its own files. They are
documented in the code because none of them is obvious, and reverting any one
of them breaks fidelity.

**Text height = font size × 0.716.** In DXF the height is the cap height, not
the font's em size. Verified across the whole distribution: 6pt→0.0597,
8pt→0.0796, 10pt→0.0995.

**...and "font size" means the vertical scale, not the geometric mean.** When
the PDF compresses text horizontally the text matrix is not uniform, and the
two scales differ. AutoCAD takes the vertical one. This matters because
PyMuPDF's `span["size"]` reports `sqrt(|ad-bc|)`, the geometric mean of both,
which is smaller by `sqrt(Tz)`: for a title at Tz = 0.40 it gives 48.73 pt
where the vertical scale is 77.04 and AutoCAD writes 77.04 × 0.716 = 55.15.
Taking the mean for the height draws the title at 63% of its size — correct in
width, squashed in height. PDFium hands over both scales separately, so the
question does not arise: height from `hypot(c, d)`, width factor from
`hypot(a, b) / hypot(c, d)`.

**Inferring that width factor from bounding boxes invents compression.**
Before the factor was read from the matrix it was inferred, by comparing the
span's bbox against the natural width of the system font. Measured against the
true value on 265 spans: every one of the 256 genuinely compressed spans was
detected, but so were 9 spans whose real factor was exactly 1.0000 — the
embedded font subset simply does not measure like the installed Arial. Those
nine were being stretched by up to 6% for no reason.

**Colours are truncated, not rounded.** AutoCAD writes (0,63,128) where
rounding gives (0,64,128). That affects ~13,700 entities in a single drawing.

**The dominant colour goes on the layer.** The most frequent colour by entity
count becomes the layer colour and those entities are left BYLAYER; only the
exceptions carry a true colour. This is not cosmetic: against the dark model
space background, a light grey written as a true colour washes out.

**Every fill at 50% transparency** (`0x0200007F`). That is what lets the
hatching show through the text background masks instead of an opaque block.

**Draw order must be written into the database, not just the table.** Writing
all polylines and then all fills leaves the masks on top of the text even when
`SORTENTSTABLE` says otherwise. Entities have to be emitted in the order the
PDF paints them.

**Sort handles must not collide** with entity handles, or AutoCAD silently
ignores the whole ordering table.

**`$EXTMIN`/`$EXTMAX` are set on the layout** (`msp.dxf.extmin`), not in the
header: ezdxf rewrites them on save. Without this the drawing opens off-screen.

**Circles are detected by shape, not by operator.** Revit PDFs contain no
Bézier curves at all: circles are exported as 20-to-40-sided polygons. And they
must be detected *before* joining segments, or joining chains them to the lines
that touch them and they stop being circular.

**Segment joining must not give up at junctions.** When several candidates
share an endpoint, follow the one that best continues the direction; bailing
out at every fork left 42% more polylines than AutoCAD.
