# Development log

These seven documents record the measurements behind the engine's larger
changes: the licence change and the PDFium port, the text height fix, the
CropBox clipping, and the image work.

They are not usage documentation — the [README](../../README.md) covers that.
They are the trail of **what was measured and against what**, which a diff
cannot carry. If you are going to change the engine, the numbers that held
before are here, along with the traps that already cost a bug.

The drawings used for the measurements belong to a real client and are not
published. They appear here only as `A-01`, `A-02`, `B-01` and so on.

The documents themselves are in Spanish.

| document | what it records |
|---|---|
| [veredicto.md](veredicto.md) | Whether AGPL could be dropped: what PDFium gives and what it does not |
| [port-etapa1.md](port-etapa1.md) | Geometry on PDFium, and its real measured cost |
| [port-etapa2.md](port-etapa2.md) | Text: the 7 fields, and exact Tz instead of inferred |
| [alturas.md](alturas.md) | Compressed text height, and how texts get matched |
| [fuera-de-hoja.md](fuera-de-hoja.md) | Invisible content PyMuPDF clipped and PDFium does not |
| [imagenes.md](imagenes.md) | PNG collisions between drawings in one batch |
| [imagenes2.md](imagenes2.md) | Rotation, blank paper, and the tile merge AutoCAD refuses |
