"""comparar.py - diferencias de propiedades entre dos DXF.

Herramienta de desarrollo, no de uso diario. Tiene dos usos:

1. REGRESION (no necesita AutoCAD). Convierte el mismo PDF antes y despues
   de tocar el motor y compara las dos salidas: muestra exactamente que
   propiedades cambiaron. Es la forma de saber si un ajuste rompio algo.

       python pdf2dxf.py plano.pdf antes.dxf
       ...cambios en el motor...
       python pdf2dxf.py plano.pdf despues.dxf
       python herramientas/comparar.py antes.dxf despues.dxf

2. FIDELIDAD (necesita AutoCAD una vez). Si tienes AutoCAD, importa el
   mismo PDF con PDFIMPORT, exportalo con DXFOUT y compara: asi se
   dedujeron las reglas que sigue este motor. Sin AutoCAD este uso no
   aplica, y no hace falta para usar pdf2dxf.

Compara cabecera, extension, longitud dibujada, tipos de entidad, grosores,
alturas y estilos de texto, propiedades de los rellenos, capas y colores.
Las filas marcadas con <- son las que difieren.
"""
import os
import sys
import math
from collections import Counter

import ezdxf


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def recoge(ruta):
    d = ezdxf.readfile(ruta)
    msp = d.modelspace()
    r = {"doc": d, "msp": msp}

    r["cabecera"] = {v: d.header.get(v, None) for v in
                     ("$INSUNITS", "$MEASUREMENT", "$LTSCALE", "$LWDISPLAY",
                      "$CELWEIGHT", "$PDMODE", "$DIMSCALE", "$ACADVER")}

    r["tipos"] = Counter(e.dxftype() for e in msp)
    r["grosor"] = Counter(e.dxf.lineweight for e in msp
                          if e.dxf.hasattr("lineweight"))

    alturas, estilos, textos = Counter(), Counter(), 0
    for e in msp:
        if e.dxftype() == "MTEXT":
            alturas[round(e.dxf.char_height, 4)] += 1
            estilos[e.dxf.style] += 1
            textos += 1
        elif e.dxftype() == "TEXT":
            alturas[round(e.dxf.height, 4)] += 1
            estilos[e.dxf.style] += 1
            textos += 1
    r["alturas"] = alturas
    r["estilos_usados"] = estilos
    r["n_textos"] = textos

    r["estilos_def"] = {}
    for st in d.styles:
        r["estilos_def"][st.dxf.name] = (
            st.dxf.get("font", ""), round(st.dxf.get("width", 1.0), 3),
            round(st.dxf.get("height", 0.0), 3))

    r["capas"] = {}
    for l in d.layers:
        tc = l.dxf.true_color if l.dxf.hasattr("true_color") else None
        r["capas"][l.dxf.name] = {
            "aci": l.dxf.color,
            "rgb": ((tc >> 16) & 255, (tc >> 8) & 255, tc & 255) if tc else None,
            "tipo_linea": l.dxf.linetype,
            "grosor": l.dxf.lineweight,
            "trazable": bool(l.dxf.plot),
        }

    h = [e for e in msp if e.dxftype() == "HATCH"]
    r["hatch"] = {
        "n": len(h),
        "solidos": sum(1 for x in h if x.dxf.solid_fill),
        "asociativos": sum(1 for x in h if x.dxf.associative),
        "estilo": Counter(x.dxf.hatch_style for x in h),
        "bordes": Counter(len(x.paths) for x in h).most_common(3),
    }

    # extension y longitud total dibujada
    xs, ys, largo = [], [], 0.0
    for e in msp:
        if e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            for i in range(len(pts) - 1):
                largo += dist(pts[i], pts[i + 1])
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
        elif e.dxftype() == "CIRCLE":
            c = e.dxf.center
            largo += 2 * math.pi * e.dxf.radius
            xs += [c.x - e.dxf.radius, c.x + e.dxf.radius]
            ys += [c.y - e.dxf.radius, c.y + e.dxf.radius]
        elif e.dxftype() == "ARC":
            largo += abs(e.dxf.end_angle - e.dxf.start_angle) / 360 * \
                     2 * math.pi * e.dxf.radius
    r["extension"] = (round(min(xs), 3), round(min(ys), 3),
                      round(max(xs), 3), round(max(ys), 3)) if xs else None
    r["largo_total"] = round(largo, 1)

    r["colores"] = Counter(
        ("rgb", e.dxf.true_color) if e.dxf.hasattr("true_color")
        else ("aci", e.dxf.color) for e in msp)
    return r


def linea(etiqueta, a, b):
    igual = "  " if a == b else "<-"
    print(f"  {etiqueta:26} {str(a)[:30]:32} {str(b)[:30]:32} {igual}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    for ruta in sys.argv[1:3]:
        if not os.path.isfile(ruta):
            print(f"No existe: {ruta}")
            return 1
    ref, mio = recoge(sys.argv[1]), recoge(sys.argv[2])
    print(f"{'':28} {'AUTOCAD':32} {'MOTOR PROPIO':32}")
    print("-" * 96)

    print("CABECERA")
    for k in ref["cabecera"]:
        linea(k, ref["cabecera"][k], mio["cabecera"][k])

    print("GEOMETRIA")
    linea("extension", ref["extension"], mio["extension"])
    linea("longitud dibujada", ref["largo_total"], mio["largo_total"])
    for t in ("LWPOLYLINE", "CIRCLE", "ARC", "HATCH", "MTEXT", "TEXT", "SOLID"):
        if ref["tipos"].get(t) or mio["tipos"].get(t):
            linea(t, ref["tipos"].get(t, 0), mio["tipos"].get(t, 0))

    print("GROSORES (1/100 mm)")
    for g in sorted(set(ref["grosor"]) | set(mio["grosor"])):
        linea(f"lineweight {g}", ref["grosor"].get(g, 0), mio["grosor"].get(g, 0))

    print("TEXTO")
    linea("total", ref["n_textos"], mio["n_textos"])
    todas = sorted(set(ref["alturas"]) | set(mio["alturas"]))
    for h in todas[:8]:
        linea(f"altura {h}", ref["alturas"].get(h, 0), mio["alturas"].get(h, 0))
    if len(todas) > 8:
        print(f"  ... {len(todas)-8} alturas mas")
    linea("estilos distintos", len(ref["estilos_usados"]), len(mio["estilos_usados"]))
    for n in sorted(set(ref["estilos_def"]) | set(mio["estilos_def"])):
        linea(f"estilo {n[:18]}", ref["estilos_def"].get(n), mio["estilos_def"].get(n))

    print("HATCH")
    for k in ("n", "solidos", "asociativos", "bordes"):
        linea(k, ref["hatch"][k], mio["hatch"][k])
    linea("hatch_style", dict(ref["hatch"]["estilo"]), dict(mio["hatch"]["estilo"]))

    print("CAPAS")
    for n in sorted(set(ref["capas"]) | set(mio["capas"])):
        a, b = ref["capas"].get(n), mio["capas"].get(n)
        linea(n, a and (a["rgb"] or a["aci"], a["tipo_linea"], a["grosor"]),
                 b and (b["rgb"] or b["aci"], b["tipo_linea"], b["grosor"]))

    print("COLORES (top 6)")
    for k, n in ref["colores"].most_common(6):
        linea(str(k), n, mio["colores"].get(k, 0))


if __name__ == "__main__":
    sys.exit(main())
