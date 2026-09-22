# Bitácora de desarrollo

*Español · [English](README.en.md)*

Estos siete documentos son el registro de las mediciones que llevaron a los
cambios grandes del motor: el cambio de licencia y el port a PDFium, la
corrección de la altura del texto, el recorte al CropBox y el pulido de las
imágenes.

No son documentación de uso — para eso está el [README](../../README.es.md) —
sino el rastro de **qué se midió y contra qué**, que es lo que un diff no
puede contar. Si vas a cambiar el motor, aquí están los números que había
antes y las trampas que ya costaron un bug.

Los planos con los que se midió son de un cliente real y no se publican. En
estos textos aparecen sólo como `A-01`, `A-02`, `B-01` y demás.

| documento | qué registra |
|---|---|
| [veredicto.md](veredicto.md) | Si se podía dejar la AGPL: qué da PDFium y qué no |
| [port-etapa1.md](port-etapa1.md) | Geometría sobre PDFium, y el coste real medido |
| [port-etapa2.md](port-etapa2.md) | Texto: los 7 campos, y el Tz exacto en vez de inferido |
| [alturas.md](alturas.md) | La altura del texto comprimido, y cómo se emparejan textos |
| [fuera-de-hoja.md](fuera-de-hoja.md) | Contenido invisible que PyMuPDF recortaba y PDFium no |
| [imagenes.md](imagenes.md) | Colisión de PNG entre planos de un mismo lote |
| [imagenes2.md](imagenes2.md) | Rotación, papel en blanco y la unión de teselas que AutoCAD rechaza |
