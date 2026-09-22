#!/usr/bin/env python3
"""Compare MTEXT heights between a reference DXF and a generated one.

    python herramientas/alturas.py reference.dxf generated.dxf

The reference is normally a drawing imported by AutoCAD's own PDFIMPORT and
exported with DXFOUT; the other one is what pdf2dxf produced from the same
PDF. Both must come from the same PDF or nothing will pair up.

Why this exists as a separate tool from comparar.py: text height is the one
property that cannot be checked by counting. A drawing can have the right
number of MTEXT entities, in the right styles, with the right colours, and
still render every compressed title at 63% of its size -- that bug shipped
once. Catching it needs each text matched to its counterpart and their
heights compared one by one.

Matching is by plain text plus insertion point, one to one, closest first.
Plain text alone is not enough: a drawing has dozens of 'NPT' at different
sizes, and pairing them by string alone crosses one with another across the
sheet and reports differences that are not there. That mistake hid a real
bug once by drowning it in noise.

The engine anchors MTEXT 1.7% of the cap height below the PDF baseline, so
that offset is undone before measuring the distance between two insertions.

Exit code is 1 when any pair falls outside the tolerance, so this can gate
a change.
"""
import argparse
import re
import sys
from collections import defaultdict

import ezdxf
from ezdxf.tools.text import plain_mtext

PREFIJO_ANCHO = re.compile(r"^\\W[+-]?(?:\d+(?:\.\d*)?|\.\d+);")

# pdf2dxf.py escribe insert.y = y - 0.017 * char_height al anclar el MTEXT.
DESPLAZAMIENTO_BASE = 0.017


def texto_plano(entidad):
    """Texto comparable: sin el prefijo \\W ni ningun otro codigo de formato."""
    return plain_mtext(PREFIJO_ANCHO.sub("", entidad.text))


def mtexts_por_texto(ruta):
    doc = ezdxf.readfile(ruta)
    indice = defaultdict(list)
    for entidad in doc.modelspace().query("MTEXT"):
        indice[texto_plano(entidad)].append(entidad)
    return indice


def distancia(referencia, generado):
    a, b = referencia.dxf.insert, generado.dxf.insert
    dx = a.x - b.x
    dy = a.y - (b.y + DESPLAZAMIENTO_BASE * generado.dxf.char_height)
    return (dx * dx + dy * dy) ** 0.5


def empareja(refs, gens, tolerancia):
    """Empareja 1:1 por texto y cercania, sin reutilizar una entidad.

    Se recorren las aristas de menor a mayor distancia: asi la entidad que ya
    encontro su vecino mas cercano no vuelve a consumirse en otro par.
    """
    pares, huerfanos_ref, huerfanos_gen = [], [], []
    for texto in set(refs) | set(gens):
        aristas = sorted(
            (distancia(a, b), i, j)
            for i, a in enumerate(refs[texto])
            for j, b in enumerate(gens[texto])
        )
        usados_ref, usados_gen = set(), set()
        for d, i, j in aristas:
            if i in usados_ref or j in usados_gen:
                continue
            if d > tolerancia:
                break
            usados_ref.add(i)
            usados_gen.add(j)
            pares.append((texto, refs[texto][i], gens[texto][j], d))
        huerfanos_ref += [t for k, t in enumerate(refs[texto]) if k not in usados_ref]
        huerfanos_gen += [t for k, t in enumerate(gens[texto]) if k not in usados_gen]
    return pares, huerfanos_ref, huerfanos_gen


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("referencia", help="DXF de referencia (p. ej. de PDFIMPORT)")
    p.add_argument("generado", help="DXF producido por pdf2dxf")
    p.add_argument("--tolerancia", type=float, default=2.0,
                   help="diferencia de altura admitida, en %% (por defecto 2)")
    p.add_argument("--distancia-max", type=float, default=0.05,
                   help="separacion maxima entre insercciones para considerar "
                        "que dos textos son el mismo, en unidades del dibujo "
                        "(por defecto 0.05)")
    p.add_argument("--listar", type=int, default=10,
                   help="cuantos casos fuera de tolerancia detallar")
    args = p.parse_args()

    refs = mtexts_por_texto(args.referencia)
    gens = mtexts_por_texto(args.generado)
    pares, sin_gen, sin_ref = empareja(refs, gens, args.distancia_max)

    if not pares:
        print("Sin pares: los dos DXF no parecen venir del mismo PDF.")
        return 1

    limite = args.tolerancia / 100.0
    fuera = []
    for texto, a, b, d in pares:
        ha, hb = a.dxf.char_height, b.dxf.char_height
        if ha <= 0:
            continue
        error = abs(hb / ha - 1.0)
        if error > limite:
            fuera.append((error, texto, ha, hb, d))
    fuera.sort(reverse=True)

    print(f"pares emparejados     : {len(pares)}")
    print(f"dentro de {args.tolerancia:g}%          : {len(pares) - len(fuera)}")
    print(f"fuera de tolerancia   : {len(fuera)}")
    print(f"sin pareja            : {len(sin_gen)} en la referencia, "
          f"{len(sin_ref)} en el generado")

    if fuera:
        print()
        print(f"{'texto':<32} {'referencia':>11} {'generado':>11} {'error':>8}")
        for error, texto, ha, hb, _ in fuera[:args.listar]:
            print(f"{texto[:32]:<32} {ha * 72:>8.2f} pt {hb * 72:>8.2f} pt "
                  f"{error:>7.2%}")
        if len(fuera) > args.listar:
            print(f"... y {len(fuera) - args.listar} mas")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
