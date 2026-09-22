# pdf2dxf

*[English](README.md) · Español*

Convierte planos **PDF vectoriales a DXF** sin AutoCAD, sin licencias y sin
servicios en la nube. Un solo archivo de Python.

Nació de comparar la salida contra la importación de AutoCAD (`PDFIMPORT`)
entidad por entidad y propiedad por propiedad, hasta reproducir su
comportamiento. En un plano de referencia de 44,360 entidades, la diferencia
en número de entidades es del **0.2%**, y la extensión, los colores de capa,
las alturas de texto y los estilos coinciden.

Y en un punto concreto lo mejora: **respeta la compresión horizontal del
texto**, que AutoCAD descarta al importar. El factor se lee directamente de la
matriz del texto, así que es exacto y no inferido — y no hace falta tener
ninguna fuente instalada para que funcione, en cualquier plataforma.

---

## Qué hace

| Elemento del PDF | Entidad DXF |
|---|---|
| Líneas y rectángulos | `LWPOLYLINE` (con segmentos contiguos unidos) |
| Polígonos circulares | `CIRCLE` |
| Curvas Bézier | `LWPOLYLINE` aplanada |
| Rellenos | `HATCH` sólido, 50% de transparencia |
| Texto | `MTEXT` editable, con la fuente y el ancho reales |
| Imágenes raster | `IMAGE` + PNG en la carpeta `PDF Images` |

Capas generadas: `PDF_Geometry`, `PDF_Text`, `PDF_Solid Fills`, `PDF_Images` —
los mismos nombres que usa AutoCAD, para no romper flujos existentes.

## Qué NO hace

- **PDF escaneados.** Si el PDF es una imagen, no hay geometría que extraer.
  Zoom sobre una línea: nítida = vectorial, pixelada = escaneo.
- **DWG.** Es formato cerrado de Autodesk y ninguna librería abierta lo
  escribe de forma fiable. DXF lo abre AutoCAD y cualquier otro CAD. Con
  `--dwg` se usa [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)
  si está instalado (gratuito, propietario, se instala aparte).
  Por honestidad: ese camino nunca se ejerció aquí, porque el conversor nunca
  se instaló. El camino probado es el de DXF.
- **Recuperar el proyecto original.** Del PDF salen geometría, texto y
  rellenos en tres capas: no hay bloques, ni capas del proyecto, ni cotas
  asociativas. Si quien emitió los planos conserva el DWG o el RVT, pedirlo
  ahorra la conversión y el repaso.

---

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python pdf2dxf.py plano.pdf                    # -> plano.dxf
python pdf2dxf.py plano.pdf salida.dxf
python pdf2dxf.py carpeta/ --batch             # -> carpeta/DXF/
python pdf2dxf.py carpeta/ --batch --dwg       # además DWG, si hay ODA
```

### Opciones

Son espejo del cuadro de diálogo *Importar PDF* de AutoCAD:

Funcionan en inglés y en español; entre corchetes, el alias.

| Opción | Efecto |
|---|---|
| `--no-join` [`--sin-unir`] | No unir segmentos contiguos |
| `--no-fills` [`--sin-rellenos`] | No importar rellenos sólidos |
| `--no-images` [`--sin-imagenes`] | No importar imágenes raster |
| `--no-text` [`--sin-texto`] | No importar texto |
| `--no-masks` [`--sin-mascaras`] | Descartar los rellenos blancos detrás del texto |
| `--layers=type` [`--capas=tipo`] | `PDF_Geometry` / `PDF_Text` / `PDF_Solid Fills` (por defecto) |
| `--layers=color` [`--capas=color`] | Una capa por color del objeto |
| `--layers=single` [`--capas=una`] | Todo en la capa 0 |
| `--arcs` [`--arcos`] | Reconstruir arcos (desactivado: puede inventar curvas) |
| `--binary` [`--binario`] | DXF binario: mismo contenido, la mitad de tamaño |
| `--batch` [`--lote`] | Convertir todos los PDF de una carpeta |
| `--dwg` | Convertir también a DWG con ODA File Converter |

### Un lote, de principio a fin

Supongamos esta carpeta de planos:

```
proyecto/
    A-02-planta-azoteas.pdf
    A-06-canalones.pdf
```

```bash
python pdf2dxf.py proyecto/ --batch
```

```
  A-02-planta-azoteas.pdf
     sheet 24.0 x 36.0 in | raw 29660 -> poly 10738, circ 135, arc 0, hatch 3131, masks dropped 0,
     text 255 (81 width-corrected), img 0
     TOTAL 14259 entities in 6.7s
  A-06-canalones.pdf
     sheet 36.0 x 24.0 in | raw 115012 -> poly 42957, circ 223, arc 0, hatch 7496, masks dropped 0,
     text 899 (143 width-corrected), img 0
     TOTAL 51575 entities in 52.3s

  batch done in 59.1s -> proyecto/DXF
```

```
proyecto/
    A-02-planta-azoteas.pdf
    A-06-canalones.pdf
    DXF/
        A-02-planta-azoteas.dxf
        A-06-canalones.dxf
```

Cómo leer la salida: **raw** son los contornos encontrados en el PDF y **poly**
en cuántas polilíneas se unieron — la diferencia entre ambos es la unión
haciendo su trabajo. Un conteo sospechosamente bajo (decenas en vez de miles)
indica que el PDF probablemente era un escaneo. Los planos con imágenes raster
generan además una carpeta `PDF Images` junto al DXF, que debe viajar con él.

### Escala

El dibujo llega en **pulgadas de papel**: una hoja de 24×36" mide 24 × 36
unidades, igual que con `PDFIMPORT`. Para milímetros reales:

```
factor = 25.4 × denominador de escala
1:50 → 1270      1:75 → 1905      1:100 → 2540
```

Conviene escalar después, plano por plano: plantas, cortes y detalles rara vez
comparten escala. Mide una cota conocida con `DIST` antes de aplicar `SCALE`.

---

## Verificar cambios

`herramientas/comparar.py` saca las diferencias de propiedades entre dos DXF.
Es una herramienta de desarrollo, no hace falta para convertir.

**Regresión** — no necesita AutoCAD. Convierte el mismo PDF antes y después de
tocar el motor y compara: muestra qué propiedades se movieron.

```bash
python pdf2dxf.py plano.pdf antes.dxf
# ...cambios en el motor...
python pdf2dxf.py plano.pdf despues.dxf
python herramientas/comparar.py antes.dxf despues.dxf
```

**Fidelidad** — solo si tienes AutoCAD. Importa el mismo PDF con `PDFIMPORT`,
expórtalo con `DXFOUT` y compara contra esa referencia. Así se dedujeron las
reglas de la sección siguiente.

Compara cabecera, extensión, longitud dibujada, tipos de entidad, grosores,
alturas y estilos de texto, propiedades de los rellenos, capas y colores. Las
filas marcadas con `<-` son las que difieren.

---

Las reglas del importador de AutoCAD que hubo que deducir para llegar hasta
aquí están en **[docs/reglas-autocad.md](docs/reglas-autocad.md)** — útiles
si vas a tocar el motor.

---

## Licencia

**MIT** — ver [LICENSE](LICENSE). Se puede usar en trabajo comercial o de
código cerrado, sin obligación de devolver nada.

Todas las dependencias son permisivas, que es lo que lo hace posible:
[pypdfium2](https://pypdfium2.readthedocs.io/) es BSD-3-Clause sobre el PDFium
de Google (Apache-2.0), [ezdxf](https://ezdxf.mozman.at/) es MIT y
[Pillow](https://python-pillow.org/) es MIT-CMU.

Las versiones anteriores eran AGPL-3.0 porque la lectura del PDF pasaba por
PyMuPDF, que es AGPL-3.0 o comercial de Artifex. La licencia nunca fue una
elección, así que se reescribió el lector sobre PDFium para quitarla.
