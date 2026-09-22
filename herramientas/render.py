#!/usr/bin/env python3
"""render.py - dibuja un DXF a PNG para mirarlo sin abrir un CAD.

Herramienta de desarrollo. Sirve para dos cosas:

1. VER una conversion desde una maquina sin AutoCAD, que es el caso normal
   si trabajas en Linux o en un servidor.

2. COMPARAR dos versiones a ojo. Los conteos de entidades y las
   propiedades los cubren comparar.py y alturas.py, pero hay fallos que
   sólo se ven mirando: una imagen colocada de lado, un relleno que tapa
   el texto, un eje que cruza donde el plano tiene un hueco. Renderiza el
   antes y el despues con el mismo recorte y ponlos lado a lado.

       python herramientas/render.py plano.dxf vista.png
       python herramientas/render.py plano.dxf detalle.png --zoom 0,0,6,3.5

El recorte va en unidades del dibujo -pulgadas de papel, si vienes de
pdf2dxf- como x0,y0,x1,y1. Sin recorte se dibuja la extension completa.

Necesita matplotlib, que no es dependencia de pdf2dxf:
    pip install matplotlib
"""
import argparse
import sys

import matplotlib
matplotlib.use("Agg")           # sin ventana: se guarda a archivo
import matplotlib.pyplot as plt

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

LADO = 17.0                     # pulgadas de figura; el alto sale del dibujo


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dxf", help="archivo DXF a dibujar")
    p.add_argument("png", help="imagen de salida")
    p.add_argument("--zoom", metavar="x0,y0,x1,y1",
                   help="recorte en unidades del dibujo; por defecto, todo")
    p.add_argument("--dpi", type=int, default=150)
    args = p.parse_args()

    doc = ezdxf.readfile(args.dxf)
    msp = doc.modelspace()

    zoom = None
    if args.zoom:
        try:
            zoom = [float(v) for v in args.zoom.split(",")]
            if len(zoom) != 4:
                raise ValueError
        except ValueError:
            p.error("--zoom espera cuatro numeros: x0,y0,x1,y1")

    if zoom:
        ancho, alto = zoom[2] - zoom[0], zoom[3] - zoom[1]
    else:
        mn, mx = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
        if not mn or not mx or abs(mn[0]) > 1e19:
            p.error("el DXF no trae $EXTMIN/$EXTMAX; usa --zoom")
        ancho, alto = mx[0] - mn[0], mx[1] - mn[1]
    if ancho <= 0 or alto <= 0:
        p.error("el area a dibujar es vacia")

    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    # Fondo blanco: el espacio modelo de AutoCAD es oscuro, pero para mirar
    # una conversion importa mas que se lean las lineas finas.
    ax.set_facecolor("white")
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(
        msp, finalize=True)

    # finalize=True redimensiona la figura y deja adjustable="datalim", con
    # lo que matplotlib descarta los limites de Y para cumplir la escala
    # 1:1 y el recorte sale con otra proporcion. Por eso el encuadre y el
    # tamano se fijan DESPUES de dibujar, no antes.
    ax.set_aspect("equal", adjustable="box")
    if zoom:
        ax.set_xlim(zoom[0], zoom[2])
        ax.set_ylim(zoom[1], zoom[3])
    ax.set_axis_off()
    fig.set_size_inches(LADO, LADO * alto / ancho)
    fig.savefig(args.png, dpi=args.dpi, facecolor="white")
    print(f"-> {args.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
