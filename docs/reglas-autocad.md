# Reglas de la importacion de AutoCAD

Como se comporta `PDFIMPORT` de AutoCAD, deducido midiendo sus propios
archivos. Cada regla esta ademas documentada en el punto del codigo que
la implementa.

---

Estas son las reglas de la importación de AutoCAD que hubo que deducir
midiendo sus archivos. Están documentadas en el código porque ninguna es
evidente, y revertir cualquiera rompe la fidelidad.

**Altura de texto = tamaño de fuente × 0.716.** En DXF la altura es la de las
mayúsculas, no el cuerpo de la fuente. Verificado en toda la distribución:
6pt→0.0597, 8pt→0.0796, 10pt→0.0995.

**...y "tamaño de fuente" es la escala vertical, no la media geométrica.**
Cuando el PDF comprime el texto en horizontal, la matriz no es uniforme y las
dos escalas difieren. AutoCAD toma la vertical. Importa porque el
`span["size"]` de PyMuPDF devuelve `sqrt(|ad-bc|)`, la media geométrica de
ambas, que es menor por `sqrt(Tz)`: en un título con Tz = 0.40 da 48.73 pt
cuando la escala vertical es 77.04 y AutoCAD escribe 77.04 × 0.716 = 55.15.
Usar la media para la altura dibuja el título al 63% de su tamaño — correcto
de ancho, achatado de alto. PDFium entrega las dos escalas por separado, así
que la duda no aparece: la altura sale de `hypot(c, d)` y el factor de ancho
de `hypot(a, b) / hypot(c, d)`.

**Inferir ese factor a partir de las cajas envolventes inventa compresión.**
Antes de leerlo de la matriz se infería, comparando la caja del span contra el
ancho natural de la fuente del sistema. Medido contra el valor real en 265
spans: se detectaron los 256 realmente comprimidos, pero también 9 cuyo factor
real era exactamente 1.0000 — el subconjunto de fuente embebido en el PDF no
mide igual que el Arial instalado. Esos nueve se estiraban hasta un 6% sin
motivo.

**Los colores se truncan, no se redondean.** AutoCAD escribe (0,63,128) donde
redondear da (0,64,128). Afecta a ~13,700 entidades de un solo plano.

**El color dominante va a la capa.** El color más frecuente por número de
entidades se pone como color de capa y esas entidades quedan en BYLAYER; solo
las excepciones llevan truecolor. No es cosmético: sobre el fondo oscuro del
espacio modelo, un gris claro como truecolor se lava.

**Todos los rellenos al 50% de transparencia** (`0x0200007F`). Es lo que
permite ver la trama por debajo de las máscaras de fondo de texto en vez de un
bloque opaco.

**El orden de dibujo se escribe en la base de datos, no solo en la tabla.**
Escribir todas las polilíneas y luego todos los rellenos deja las máscaras
encima del texto aunque la `SORTENTSTABLE` diga lo contrario. Hay que emitir
las entidades en el orden en que el PDF pinta.

**Los handles de la tabla de ordenación no pueden colisionar** con los de las
entidades, o AutoCAD ignora la tabla entera en silencio.

**`$EXTMIN`/`$EXTMAX` se fijan en el layout** (`msp.dxf.extmin`), no en la
cabecera: ezdxf los reescribe al guardar. Sin eso el plano abre descuadrado.

**Los círculos se detectan por forma, no por operador.** Los PDF de Revit no
traen ni una sola curva Bézier: exportan los círculos como polígonos de 20 a
40 lados. Y hay que detectarlos *antes* de unir segmentos, o la unión los
encadena con las líneas que los tocan y dejan de ser circulares.

**La unión de segmentos no puede rendirse en los cruces.** Al encontrar varios
candidatos hay que seguir el que mejor continúa la dirección; abandonar en
cada bifurcación dejaba un 42% más de polilíneas que AutoCAD.
