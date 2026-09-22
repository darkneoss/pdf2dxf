#!/usr/bin/env python
# Copyright (C) 2026  darkneoss
#
# Este programa es software libre: puede redistribuirlo y modificarlo bajo
# los terminos de la GNU Affero General Public License version 3, tal como
# la publica la Free Software Foundation. Vease el archivo LICENSE.
#
# Se distribuye con la esperanza de que sea util, pero SIN GARANTIA ALGUNA.
#
# La licencia vigente del proyecto consta en LICENSE.
"""
pdf2dxf.py - vector PDF to DXF converter. No AutoCAD, no licences, no cloud.

Translates the PDF drawing operators into DXF entities:
    lines and rectangles -> LWPOLYLINE (contiguous segments joined)
    circular polygons    -> CIRCLE
    Bezier curves        -> flattened LWPOLYLINE
    fills                -> solid HATCH, 50% transparency
    text                 -> editable MTEXT, real font and width
    raster images        -> IMAGE + PNG files in a "PDF Images" folder

Units: paper inches (1 unit = 1 inch), the same as AutoCAD's PDFIMPORT, so
the scaling step afterwards is identical:
    factor to real millimetres = 25.4 x scale denominator

Layers: PDF_Geometry, PDF_Text, PDF_Solid Fills, PDF_Images -- the same names
AutoCAD uses, so existing workflows keep working.

Usage:
    python pdf2dxf.py drawing.pdf [output.dxf] [options]
    python pdf2dxf.py folder/ --batch [options]

Options (mirroring AutoCAD's Import PDF dialog).
Spanish aliases in brackets still work:
    --no-join        [--sin-unir]      do not join contiguous segments
    --no-fills       [--sin-rellenos]  do not import solid fills
    --no-images      [--sin-imagenes]  do not import raster images
    --no-text        [--sin-texto]     do not import text
    --no-masks       [--sin-mascaras]  drop the white fills behind text
    --layers=type    [--capas=tipo]    PDF_Geometry / PDF_Text / ... (default)
    --layers=color   [--capas=color]   one layer per object colour
    --layers=single  [--capas=una]     everything on layer 0
    --arcs           [--arcos]         rebuild arcs (off: may invent curves)
    --binary         [--binario]       binary DXF (half the size)
    --batch          [--lote]          convert every PDF in a folder
    --dwg                              also convert to DWG with ODA File
                                       Converter if installed (free, separate
                                       download; DWG is a closed format and no
                                       open library writes it reliably)
"""

import os
import sys
import math
import time
import ctypes
from pathlib import Path

import ezdxf         # escritura del DXF
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

PUNTOS_POR_PULGADA = 72.0
SEGMENTOS_BEZIER = 8          # tramos por curva al aplanar
RADIO_MAXIMO = 60.0           # pulgadas: mas grande que cualquier hoja
DESVIO_MAXIMO = 0.004         # pulgadas de desviacion admitida al ajustar
TOLERANCIA_UNION = 1e-6       # pulgadas; para encadenar segmentos

CAPA_GEOM  = "PDF_Geometry"
CAPA_TEXTO = "PDF_Text"
CAPA_RELL  = "PDF_Solid Fills"
CAPA_IMG   = "PDF_Images"

# Valor crudo del grupo 440 que escribe AutoCAD en cada relleno: la marca
# 0x02000000 mas alfa 127, es decir 50% de transparencia. Se pone crudo
# porque pasarlo como fraccion 0.5 redondea a alfa 128 y no coincide.
TRANSPARENCIA_RELLENO = 0x0200007F

# Mapa de fuentes PDF -> TTF de Windows. Sin esto el texto se escribe con el
# estilo por defecto, mas ancho que Arial Narrow, y se desborda de las celdas
# del cuadro de rotulo.
# El nombre de estilo lleva prefijo "PDF " igual que los que crea AutoCAD
# al importar, y el ultimo valor es la CAP HEIGHT de la familia: en DXF la
# altura del texto es la de las mayusculas, no el cuerpo de la fuente.
FUENTES = [
    ("narrow",  "bold",  "arialnb.ttf", "PDF Arial Narrow Bold", 0.716),
    ("narrow",  None,    "arialn.ttf",  "PDF Arial Narrow",      0.716),
    ("arial",   "bold",  "arialbd.ttf", "PDF Arial Bold",        0.716),
    ("arial",   None,    "arial.ttf",   "PDF Arial",             0.716),
    ("times",   None,    "times.ttf",   "PDF Times",             0.662),
]
CAP_POR_DEFECTO = 0.716


# ---------------------------------------------------------------- utilidades

UMBRAL_NEGRO = 0.12      # por debajo de esto se considera negro de dibujo
UMBRAL_BLANCO = 0.98     # por encima de esto, relleno blanco (mascara)


def es_blanco(rgb):
    """Relleno blanco: casi siempre una mascara de fondo de texto.

    Los planos traen rectangulos blancos detras de cada etiqueta para tapar
    la trama y que el texto se lea. En el PDF no se ven (blanco sobre
    blanco), pero son entidades reales y AutoCAD tambien las importa.
    """
    return rgb is not None and all(c >= UMBRAL_BLANCO for c in rgb)


def es_negro(rgb):
    return rgb is None or all(c <= UMBRAL_NEGRO for c in rgb)


def color_dominante(trazos, relleno):
    """Color mas frecuente entre los trazos de un tipo, ignorando el negro.

    AutoCAD hace justo esto al importar: pone el color dominante COMO COLOR
    DE LA CAPA y deja esas entidades en BYLAYER, reservando el truecolor
    explicito para las excepciones. La diferencia no es cosmetica: sobre el
    fondo oscuro del espacio modelo, un gris claro escrito como truecolor se
    lava, mientras que por capa se controla de un tiro y el dibujo se lee.
    """
    from collections import Counter
    c = Counter()
    for t in trazos:
        if bool(t.relleno) != relleno or es_negro(t.color):
            continue
        c[t.color] += 1
    return c.most_common(1)[0][0] if c else None


def atributos_color(rgb, dominante=None):
    """Atributos DXF de color para un trazo del PDF.

    El negro puro NO se escribe como truecolor 0,0,0: en AutoCAD el espacio
    modelo tiene fondo negro y el dibujo se volveria invisible. Se usa el
    color indice 7, que se dibuja blanco sobre fondo oscuro y negro al
    imprimir. Es lo que hace la importacion de AutoCAD, y por eso sus DWG se
    ven bien y los primeros DXF de este motor salian todos negros.
    """
    if es_negro(rgb):
        return {"color": 7}
    if dominante is not None and rgb == dominante:
        return {"color": 256}          # BYLAYER: lo pone la capa
    r, g, b = rgb255(rgb)
    return {"color": 256, "true_color": (r << 16) | (g << 8) | b}


def rgb255(rgb):
    """0..1 -> 0..255 TRUNCANDO, no redondeando.

    AutoCAD trunca: escribe (0,63,128) donde el redondeo da (0,64,128). Son
    ~13,700 entidades de un solo plano que dejarian de coincidir por un bit.
    """
    return (tuple(max(0, min(255, int(c * 255))) for c in rgb)
            if rgb else (0, 0, 0))


def bezier(p0, p1, p2, p3, n=SEGMENTOS_BEZIER):
    """Aplana una bezier cubica en n segmentos rectos."""
    pts = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        x = (u**3 * p0[0] + 3 * u*u*t * p1[0] + 3 * u*t*t * p2[0] + t**3 * p3[0])
        y = (u**3 * p0[1] + 3 * u*u*t * p1[1] + 3 * u*t*t * p2[1] + t**3 * p3[1])
        pts.append((x, y))
    return pts


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# Grosores que admite DXF, en centesimas de milimetro. Cualquier otro valor
# es invalido, asi que el ancho del PDF se ajusta al mas cercano.
GROSORES = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80,
            90, 100, 106, 120, 140, 158, 200, 211]


def grosor_dxf(ancho_puntos):
    """Ancho de trazo del PDF (puntos) -> lineweight DXF (1/100 mm)."""
    if not ancho_puntos:
        return -1                      # -1 = por capa
    centesimas = ancho_puntos * 25.4 / 72.0 * 100.0
    return min(GROSORES, key=lambda g: abs(g - centesimas))


def recorta_segmento(p, q, caja):
    """Liang-Barsky: recorta el segmento p-q a la caja, o None si queda fuera."""
    x0, y0, x1, y1 = caja
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for num, den in ((p[0] - x0, -dx), (x1 - p[0], dx),
                     (p[1] - y0, -dy), (y1 - p[1], dy)):
        if den == 0:
            if num < 0:
                return None
            continue
        t = num / den
        if den < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return ((p[0] + t0 * dx, p[1] + t0 * dy),
            (p[0] + t1 * dx, p[1] + t1 * dy))


def recorta_abierto(pts, caja):
    """Recorta una polilinea abierta; devuelve la lista de tramos que quedan."""
    tramos, actual = [], []
    for i in range(len(pts) - 1):
        r = recorta_segmento(pts[i], pts[i + 1], caja)
        if r is None:
            if len(actual) > 1:
                tramos.append(actual)
            actual = []
            continue
        a, b = r
        if not actual:
            actual = [a, b]
        elif dist(actual[-1], a) <= 1e-9:
            actual.append(b)
        else:
            if len(actual) > 1:
                tramos.append(actual)
            actual = [a, b]
    if len(actual) > 1:
        tramos.append(actual)
    return tramos


def recorta_cerrado(pts, caja):
    """Sutherland-Hodgman: recorta un poligono relleno a la caja."""
    x0, y0, x1, y1 = caja

    def dentro(p, borde):
        return (p[0] >= x0 if borde == 0 else
                p[0] <= x1 if borde == 1 else
                p[1] >= y0 if borde == 2 else p[1] <= y1)

    def corte(a, b, borde):
        if borde in (0, 1):
            xv = x0 if borde == 0 else x1
            t = (xv - a[0]) / (b[0] - a[0])
            return (xv, a[1] + t * (b[1] - a[1]))
        yv = y0 if borde == 2 else y1
        t = (yv - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), yv)

    salida = list(pts)
    for borde in range(4):
        entrada, salida = salida, []
        if not entrada:
            break
        ant = entrada[-1]
        for act in entrada:
            if dentro(act, borde):
                if not dentro(ant, borde):
                    salida.append(corte(ant, act, borde))
                salida.append(act)
            elif dentro(ant, borde):
                salida.append(corte(ant, act, borde))
            ant = act
    return salida


class Lienzo:
    """Coordenadas relativas al CropBox, origen arriba-izquierda, puntos ->
    coordenadas DXF (origen abajo-izquierda, pulgadas)."""

    def __init__(self, alto_puntos):
        self.alto = alto_puntos

    def __call__(self, p):
        x = p[0] if not hasattr(p, "x") else p.x
        y = p[1] if not hasattr(p, "y") else p.y
        return (x / PUNTOS_POR_PULGADA,
                (self.alto - y) / PUNTOS_POR_PULGADA)


class Trazo:
    """Un contorno listo para escribir.

    'orden' conserva la posicion original en el PDF. Es necesario: si se
    reordenan las entidades, un relleno que iba debajo puede quedar encima
    y tapar lo que hay abajo (los globos de eje salian negros por esto).
    """
    __slots__ = ("pts", "cerrado", "color", "relleno", "orden", "grosor",
                 "grupo", "par_impar", "circulo")

    def __init__(self, pts, cerrado, color, relleno, orden, grosor=-1,
                 grupo=-1, par_impar=False, circulo=None):
        self.pts, self.cerrado = pts, cerrado
        self.color, self.relleno, self.orden = color, relleno, orden
        self.grosor, self.grupo = grosor, grupo
        self.par_impar = par_impar
        self.circulo = circulo


# ------------------------------------------------------------------ geometria

def extraer_trazos(pagina, conv):
    """Extrae paths con PDFium y los adapta al contrato de ``Trazo``.

    PDFium conserva las coordenadas de usuario crudas, mientras que ``conv``
    espera las de PyMuPDF: relativas al CropBox y con Y hacia abajo.
    """
    trazos = []
    contador = [0]

    grosor = [-1]
    grupo = [-1]
    par_impar = [False]
    recorte = [None]
    crop_x0, crop_y0, crop_x1, crop_y1 = pagina.get_cropbox()
    alto_crop = crop_y1 - crop_y0
    cache_recortes = {}
    cache_recortes_rapidos = {}

    def punto_crudo(segmento):
        x, y = ctypes.c_float(), ctypes.c_float()
        if not pdfium_raw.FPDFPathSegment_GetPoint(segmento, x, y):
            return None
        return x.value, y.value

    def punto(segmento, matriz=(1, 0, 0, 1, 0, 0)):
        crudo = punto_crudo(segmento)
        if crudo is None:
            return None
        a, b, c, d, e, f = matriz
        x, y = a * crudo[0] + c * crudo[1] + e, \
               b * crudo[0] + d * crudo[1] + f
        # Sin restar el CropBox, los planos cuyo MediaBox está centrado en
        # (0, 0) quedan fuera de la hoja al pasar a coordenadas DXF.
        return conv((x - crop_x0, alto_crop - (y - crop_y0)))

    def color_de(lector, objeto):
        canales = [ctypes.c_uint() for _ in range(4)]
        if not lector(objeto, *canales):
            return None
        return tuple(c.value / 255.0 for c in canales[:3])

    def recorte_de(objeto):
        """Devuelve la caja del clip efectivo, cacheada por su geometría.

        PDFium entrega un handle distinto para cada objeto incluso si el clip
        es el mismo. Por eso la clave usa paths, segmentos y caja, nunca la
        identidad del handle.
        """
        clip = pdfium_raw.FPDFPageObj_GetClipPath(objeto)
        if not clip:
            return None
        n_paths = pdfium_raw.FPDFClipPath_CountPaths(clip)
        if n_paths <= 0:
            return None
        conteos = [pdfium_raw.FPDFClipPath_CountPathSegments(clip, i)
                   for i in range(n_paths)]
        if not any(conteos):
            return None
        primero = punto_crudo(pdfium_raw.FPDFClipPath_GetPathSegment(clip, 0, 0))
        ultimo_i = next(i for i in range(n_paths - 1, -1, -1) if conteos[i])
        ultimo = punto_crudo(pdfium_raw.FPDFClipPath_GetPathSegment(
            clip, ultimo_i, conteos[ultimo_i] - 1))
        if primero is None or ultimo is None:
            return None
        # La mayoría de los objetos repite exactamente el mismo clip. Dos
        # vértices extremos, estructura y conteos permiten saltar su lectura
        # completa; la entrada almacenada conserva además la caja entera.
        firma_rapida = (n_paths, tuple(conteos),
                         tuple(round(v, 6) for v in primero + ultimo))
        if firma_rapida in cache_recortes_rapidos:
            return cache_recortes_rapidos[firma_rapida]
        xs, ys = [], []
        for i, n_segmentos in enumerate(conteos):
            for j in range(n_segmentos):
                segmento = pdfium_raw.FPDFClipPath_GetPathSegment(clip, i, j)
                p = punto_crudo(segmento)
                if p is not None:
                    xs.append(p[0])
                    ys.append(p[1])
        if not xs:
            return None
        # El clip efectivo ya está en espacio de página; los paths normales
        # no necesariamente lo están (pueden llevar matriz de Form XObject).
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        a = conv((x0 - crop_x0, alto_crop - (y0 - crop_y0)))
        b = conv((x1 - crop_x0, alto_crop - (y1 - crop_y0)))
        caja = (min(a[0], b[0]), min(a[1], b[1]),
                max(a[0], b[0]), max(a[1], b[1]))
        firma = (n_paths, tuple(conteos),
                 tuple(round(v, 6) for v in caja))
        if firma in cache_recortes:
            caja = cache_recortes[firma]
        else:
            cache_recortes[firma] = caja
        cache_recortes_rapidos[firma_rapida] = caja
        return caja

    def emitir(pts, cerrado, color, relleno, circulo=None, caja_trazo=None):
        caja = recorte[0]
        if caja is not None:
            # si cabe entero dentro, no hay nada que recortar
            if caja_trazo is None:
                xs = [q[0] for q in pts]
                ys = [q[1] for q in pts]
                caja_trazo = (min(xs), min(ys), max(xs), max(ys)) if xs else None
            if not (caja_trazo is not None and caja[0] <= caja_trazo[0]
                    and caja_trazo[2] <= caja[2]
                    and caja[1] <= caja_trazo[1]
                    and caja_trazo[3] <= caja[3]):
                if relleno or cerrado:
                    pts = recorta_cerrado(pts, caja)
                    if len(pts) < 3:
                        return
                else:
                    for tramo in recorta_abierto(pts, caja):
                        _emitir(tramo, cerrado, color, relleno)
                    return
        _emitir(pts, cerrado, color, relleno, circulo)

    def _emitir(pts, cerrado, color, relleno, circulo=None):
        # El circulo se detecta AQUI, antes de unir segmentos: la union lo
        # encadenaria con las lineas que lo tocan y dejaria de ser circular.
        circ = es_circulo(pts) if circulo is None else circulo
        trazos.append(Trazo(pts, cerrado or bool(circ), color, relleno,
                            contador[0], grosor[0], grupo[0], par_impar[0],
                            circ))
        contador[0] += 1

    def emitir_actual(pts, cerrado, color, relleno, caja_trazo):
        # PDFium suele materializar el último segmento de ``h`` hasta el
        # punto inicial; PyMuPDF sólo marcaba closePath. Conservamos el mismo
        # contrato (vértices sin repetir + cerrado) para no sumar el borde
        # final dos veces al escribir/comparar la polilínea.
        circulo = es_circulo(pts)
        if cerrado and not relleno and len(pts) > 2 and \
                dist(pts[0], pts[-1]) <= TOLERANCIA_UNION:
            pts = pts[:-1]
        emitir(pts, cerrado, color, relleno, circulo, caja_trazo)

    # get_objects() desciende en Form XObjects. Su iteración es el orden de
    # pintura que el motor conserva para hatches y tabla de redraw.
    for n_objeto, obj in enumerate(pagina.get_objects(max_depth=15)):
        if obj.type != pdfium_raw.FPDF_PAGEOBJ_PATH:
            continue
        objeto = obj.raw
        matriz = obj.get_matrix().get()
        fill_mode, stroke = ctypes.c_long(), ctypes.c_long()
        if not pdfium_raw.FPDFPath_GetDrawMode(objeto, fill_mode, stroke):
            continue
        relleno = fill_mode.value != pdfium_raw.FPDF_FILLMODE_NONE
        color = color_de(pdfium_raw.FPDFPageObj_GetFillColor if relleno
                         else pdfium_raw.FPDFPageObj_GetStrokeColor, objeto)
        ancho = ctypes.c_float()
        pdfium_raw.FPDFPageObj_GetStrokeWidth(objeto, ancho)
        grosor[0] = grosor_dxf(ancho.value) if stroke.value else -1
        par_impar[0] = fill_mode.value == pdfium_raw.FPDF_FILLMODE_ALTERNATE
        grupo[0] = n_objeto
        recorte[0] = recorte_de(objeto)

        actual, cerrado = [], False
        x_min = x_max = y_min = y_max = None
        n_segmentos = pdfium_raw.FPDFPath_CountSegments(objeto)
        i = 0
        while i < n_segmentos:
            segmento = pdfium_raw.FPDFPath_GetPathSegment(objeto, i)
            tipo = pdfium_raw.FPDFPathSegment_GetType(segmento)
            p = punto(segmento, matriz)
            if p is None:
                i += 1
                continue
            if tipo == pdfium_raw.FPDF_SEGMENT_MOVETO:
                if len(actual) > 1:
                    emitir_actual(actual, cerrado or relleno, color, relleno,
                                  (x_min, y_min, x_max, y_max))
                actual, cerrado = [p], False
                x_min = x_max = p[0]
                y_min = y_max = p[1]
            elif tipo == pdfium_raw.FPDF_SEGMENT_LINETO:
                if not actual:
                    actual = [p]
                    x_min = x_max = p[0]
                    y_min = y_max = p[1]
                else:
                    actual.append(p)
                    x_min = p[0] if p[0] < x_min else x_min
                    x_max = p[0] if p[0] > x_max else x_max
                    y_min = p[1] if p[1] < y_min else y_min
                    y_max = p[1] if p[1] > y_max else y_max
                cerrado = cerrado or bool(pdfium_raw.FPDFPathSegment_GetClose(segmento))
            elif tipo == pdfium_raw.FPDF_SEGMENT_BEZIERTO:
                # Una cúbica aparece como tres BEZIERTO: dos controles y el
                # destino. PDFium no agrupa esos tres segmentos por nosotros.
                if i + 2 < n_segmentos and actual:
                    s2 = pdfium_raw.FPDFPath_GetPathSegment(objeto, i + 1)
                    s3 = pdfium_raw.FPDFPath_GetPathSegment(objeto, i + 2)
                    p2, p3 = punto(s2, matriz), punto(s3, matriz)
                    if (pdfium_raw.FPDFPathSegment_GetType(s2) ==
                            pdfium_raw.FPDF_SEGMENT_BEZIERTO and
                            pdfium_raw.FPDFPathSegment_GetType(s3) ==
                            pdfium_raw.FPDF_SEGMENT_BEZIERTO and
                            p2 is not None and p3 is not None):
                        nuevos = bezier(actual[-1], p, p2, p3)
                        actual.extend(nuevos)
                        for q in nuevos:
                            x_min = q[0] if q[0] < x_min else x_min
                            x_max = q[0] if q[0] > x_max else x_max
                            y_min = q[1] if q[1] < y_min else y_min
                            y_max = q[1] if q[1] > y_max else y_max
                        cerrado = cerrado or bool(
                            pdfium_raw.FPDFPathSegment_GetClose(s3))
                        i += 2
                    else:
                        actual.append(p)
                        x_min = p[0] if p[0] < x_min else x_min
                        x_max = p[0] if p[0] > x_max else x_max
                        y_min = p[1] if p[1] < y_min else y_min
                        y_max = p[1] if p[1] > y_max else y_max
                else:
                    actual.append(p)
                    x_min = p[0] if p[0] < x_min else x_min
                    x_max = p[0] if p[0] > x_max else x_max
                    y_min = p[1] if p[1] < y_min else y_min
                    y_max = p[1] if p[1] > y_max else y_max
            i += 1
        if len(actual) > 1:
            emitir_actual(actual, cerrado or relleno, color, relleno,
                          (x_min, y_min, x_max, y_max))

    return trazos


def direccion(p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n else None


def mejor_continuacion(cadena, vecinos, abiertos):
    """De varios trazos que salen del mismo punto, el que sigue mas recto."""
    if len(vecinos) == 1:
        return vecinos[0]
    salida = direccion(cadena[-2], cadena[-1]) if len(cadena) >= 2 else None
    if salida is None:
        return vecinos[0]
    mejor, mejor_cos = None, -2.0
    for j in vecinos:
        pts = abiertos[j].pts
        if dist(cadena[-1], pts[0]) <= TOLERANCIA_UNION:
            d = direccion(pts[0], pts[1])
        elif dist(cadena[-1], pts[-1]) <= TOLERANCIA_UNION:
            d = direccion(pts[-1], pts[-2])
        else:
            continue
        if d is None:
            continue
        cos = salida[0] * d[0] + salida[1] * d[1]
        if cos > mejor_cos:
            mejor, mejor_cos = j, cos
    return mejor


def es_arco(pts, tol=0.006):
    """Arco de circunferencia: devuelve (centro, radio, ang_ini, ang_fin).

    AutoCAD reconstruye arcos ademas de circulos (149 en un solo plano).
    Aqui llegan como cadenas de segmentos rectos, asi que se comprueba que
    todos los puntos equidisten de un centro estimado por tres puntos.
    """
    if len(pts) < 6:
        return None
    a, b, c = pts[0], pts[len(pts) // 2], pts[-1]
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    ax, ay = a; bx, by = b; cx_, cy_ = c
    ux = ((ax*ax + ay*ay) * (by - cy_) + (bx*bx + by*by) * (cy_ - ay)
          + (cx_*cx_ + cy_*cy_) * (ay - by)) / d
    uy = ((ax*ax + ay*ay) * (cx_ - bx) + (bx*bx + by*by) * (ax - cx_)
          + (cx_*cx_ + cy_*cy_) * (bx - ax)) / d
    radios = [math.hypot(p[0] - ux, p[1] - uy) for p in pts]
    r = sum(radios) / len(radios)
    if r <= 0:
        return None

    # Tres filtros que evitan inventar arcos gigantes. Sin ellos, cualquier
    # cadena larga y casi recta se ajusta a una circunferencia enorme: con
    # tolerancia relativa del 0.6% sobre un radio de 200", la desviacion
    # admitida pasa de una pulgada y aparecen arcos que cruzan el plano.
    if r > RADIO_MAXIMO:                       # nada mayor que la hoja
        return None
    if (max(radios) - min(radios)) > DESVIO_MAXIMO:   # limite absoluto
        return None
    if (max(radios) - min(radios)) / r > tol:         # limite relativo
        return None
    cuerda = dist(pts[0], pts[-1])
    if cuerda <= 0.1 * r:                     # cerrado: es circulo, no arco
        return None
    if cuerda / (2 * r) < 0.05:               # abertura angular ridicula
        return None
    ang = lambda p: math.degrees(math.atan2(p[1] - uy, p[0] - ux))
    a0, a1 = ang(pts[0]), ang(pts[-1])
    # el sentido lo da el punto medio
    am = ang(pts[len(pts) // 2])
    def entre(x, y, z):
        x, y, z = x % 360, y % 360, z % 360
        return (x < y < z) if x < z else (y > x or y < z)
    if not entre(a0, am, a1):
        a0, a1 = a1, a0
    return (ux, uy), r, a0, a1


def unir_trazos(trazos):
    """Encadena trazos abiertos que comparten extremo y color.

    Es lo que hace 'unir segmentos contiguos' de AutoCAD, y la razon de que
    un plano pase de decenas de miles de lineas sueltas a miles de
    polilineas. La cadena hereda el 'orden' mas bajo de sus piezas, para no
    alterar el orden de pintado.
    """
    abiertos, salida = [], []
    for t in trazos:
        (salida if (t.cerrado or t.relleno) else abiertos).append(t)

    def clave(p):
        return (round(p[0], 6), round(p[1], 6))

    extremos = {}
    for i, t in enumerate(abiertos):
        extremos.setdefault(clave(t.pts[0]),  []).append(i)
        extremos.setdefault(clave(t.pts[-1]), []).append(i)

    usado = [False] * len(abiertos)
    for i in range(len(abiertos)):
        if usado[i]:
            continue
        usado[i] = True
        base = abiertos[i]
        cadena = list(base.pts)
        orden = base.orden

        for _ in range(2):
            while True:
                vecinos = [j for j in extremos.get(clave(cadena[-1]), [])
                           if not usado[j] and abiertos[j].color == base.color]
                if not vecinos:
                    break
                # Con varios candidatos NO hay que rendirse: se sigue el que
                # mejor continua la direccion actual. Rendirse en cada cruce
                # dejaba un 42% mas de polilineas que la importacion de
                # AutoCAD sobre el mismo plano.
                j = mejor_continuacion(cadena, vecinos, abiertos)
                if j is None:
                    break
                otro = abiertos[j]
                if dist(cadena[-1], otro.pts[0]) <= TOLERANCIA_UNION:
                    cadena.extend(otro.pts[1:])
                elif dist(cadena[-1], otro.pts[-1]) <= TOLERANCIA_UNION:
                    cadena.extend(reversed(otro.pts[:-1]))
                else:
                    break
                usado[j] = True
                orden = min(orden, otro.orden)
            cadena.reverse()

        # Reintentar la deteccion de circulo AQUI: una circunferencia
        # partida en dos mitades en el PDF solo se reconoce una vez
        # encadenada, y AutoCAD las reconstruye (287 circulos contra 97).
        circ = es_circulo(cadena)
        salida.append(Trazo(cadena, bool(circ), base.color, False,
                            orden, base.grosor, base.grupo,
                            base.par_impar, circ))

    salida.sort(key=lambda t: t.orden)
    return salida


# --------------------------------------------------------------------- texto

def estilo_para(dxf, nombre_fuente, cache):
    """Estilo DXF y cap height para la fuente del PDF."""
    f = (nombre_fuente or "").lower()
    for marca, negrita, ttf, estilo, cap in FUENTES:
        if marca in f and (negrita is None or negrita in f):
            if estilo not in cache:
                if estilo not in dxf.styles:
                    dxf.styles.add(estilo, font=ttf)
                cache.add(estilo)
            return estilo, cap, ttf
    return "Standard", CAP_POR_DEFECTO, "arial.ttf"


def escapa_mtext(t):
    """MTEXT trata \\, { y } como formato; hay que escaparlos."""
    return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def extraer_texto(pagina, conv):
    """Extrae objetos de texto PDFium con su escala real de matriz.

    ``get_objects()`` devuelve el orden de pintura, que tambien determina el
    orden de los MTEXT.  PDFium deja esos objetos sin TextPage, asi que se la
    asociamos antes de llamar ``extract()``.
    """
    def color_relleno(objeto):
        canales = [ctypes.c_uint() for _ in range(4)]
        if not pdfium_raw.FPDFPageObj_GetFillColor(objeto, *canales):
            return 0
        return ((canales[0].value << 16) | (canales[1].value << 8)
                | canales[2].value)

    objetos = []
    textpage = pagina.get_textpage()
    crop_x0, crop_y0, crop_x1, crop_y1 = pagina.get_cropbox()
    alto_crop = crop_y1 - crop_y0
    for obj in pagina.get_objects(max_depth=15):
        if obj.type != pdfium_raw.FPDF_PAGEOBJ_TEXT:
            continue
        obj.textpage = textpage
        try:
            texto = obj.extract()
        except Exception:
            continue
        if not texto:
            continue

        matriz = obj.get_matrix()
        a, b, c, d, e, f = (matriz.a, matriz.b, matriz.c,
                             matriz.d, matriz.e, matriz.f)
        escala_horizontal = math.hypot(a, b)
        escala_vertical = math.hypot(c, d)
        tz = escala_horizontal / escala_vertical if escala_vertical else 1.0
        try:
            fuente = obj.get_font().get_base_name()
        except Exception:
            fuente = ""
        # PDFium usa el origen inferior izquierdo y coordenadas crudas; conv
        # espera el origen superior izquierdo relativo al CropBox.
        ins = conv((e - crop_x0, alto_crop - (f - crop_y0)))
        izquierda, abajo, derecha, arriba = obj.get_bounds()
        objetos.append({
            "texto": texto,
            "ins": ins, "a": a, "b": b, "e": e, "f": f,
            "caja": (izquierda, abajo, derecha, arriba),
            "escala_vertical": escala_vertical,
            "tz": tz,
            "rot": math.degrees(math.atan2(b, a)),
            "color": color_relleno(obj.raw),
            "fuente": fuente,
        })

    for objeto in objetos:
        texto = objeto["texto"].strip()
        # Algunos espacios separadores quedan al final de un objeto PDFium
        # cuando el siguiente continua la misma linea. Se conservan solo si
        # la siguiente caja empieza a distancia tipografica: asi no se
        # pierden al limpiar el artefacto de borde, ni se agregan espacios a
        # etiquetas independientes que terminan con uno en el contenido PDF.
        if objeto["texto"].endswith((" ", "\t", "\r", "\n")):
            a, b = objeto["a"], objeto["b"]
            escala = math.hypot(a, b)
            if escala:
                ux, uy = a / escala, b / escala
                vx, vy = -uy, ux
                e, f = objeto["e"], objeto["f"]
                l, abajo, r, arriba = objeto["caja"]
                fin = max((x - e) * ux + (y - f) * uy
                          for x, y in ((l, abajo), (l, arriba),
                                       (r, abajo), (r, arriba)))
                for siguiente in objetos:
                    if siguiente is objeto or not siguiente["texto"].strip():
                        continue
                    da = siguiente["e"] - e
                    df = siguiente["f"] - f
                    avance = da * ux + df * uy - fin
                    lateral = da * vx + df * vy
                    giro = abs(a * siguiente["b"] - b * siguiente["a"])
                    if (-0.1 <= avance <= 6.0 and abs(lateral) <= 1.0
                            and giro <= 0.01 * escala
                            * math.hypot(siguiente["a"], siguiente["b"])):
                        texto += " "
                        break
        objeto["texto"] = texto
    return objetos


# ------------------------------------------------------------------ imagenes

def extraer_imagenes(pagina, conv, dxf, msp, carpeta_img, nombre_dibujo):
    """Guarda las imagenes raster como PNG y las referencia desde el DXF.

    AutoCAD hace lo mismo con su carpeta 'PDF Images': el DXF no incrusta la
    imagen, la referencia. Si la carpeta se separa del DXF, el plano abre con
    las imagenes perdidas.
    """
    # En un lote todos los DXF comparten "PDF Images". El prefijo por dibujo
    # evita que img_0000.png de un plano reemplace el de otro, sin dejar de
    # usar una ruta relativa que pueda viajar junto con el DXF.
    stem = Path(nombre_dibujo).stem
    seguro = "".join("_" if ord(c) < 32 or c in '<>:\"/\\|?*' else c
                     for c in stem).rstrip(". ")
    if seguro != stem:
        # Los nombres validos de Windows conservan su stem legible; para uno
        # invalido en Windows agregamos una huella corta para no colisionar al
        # sustituir caracteres prohibidos.
        import hashlib
        seguro = "%s_%s" % (seguro or "drawing",
                             hashlib.sha1(stem.encode("utf-8")).hexdigest()[:8])
    nombre_dibujo = seguro or "drawing"

    crop_x0, crop_y0, crop_x1, crop_y1 = pagina.get_cropbox()
    alto_crop = crop_y1 - crop_y0
    n = 0
    for k, objeto in enumerate(pagina.get_objects(max_depth=15)):
        if objeto.type != pdfium_raw.FPDF_PAGEOBJ_IMAGE:
            continue
        try:
            ancho_px, alto_px = objeto.get_px_size()
            bitmap = objeto.get_bitmap(render=False)
            imagen = bitmap.to_pil()
            carpeta_img.mkdir(parents=True, exist_ok=True)
            ruta = carpeta_img / f"{nombre_dibujo}_{k:04d}.png"
            imagen.save(ruta)
        except Exception:
            continue

        try:
            izquierda, abajo, derecha, arriba = objeto.get_bounds()
        except Exception:
            continue
        # PDFium entrega coordenadas crudas, origen abajo-izquierda. ``conv``
        # usa el contrato heredado: origen arriba-izquierda relativo al
        # CropBox. Esta es la misma normalizacion de trazos y texto.
        x0, y0 = conv((izquierda - crop_x0, alto_crop - (abajo - crop_y0)))
        x1, y1 = conv((derecha - crop_x0, alto_crop - (arriba - crop_y0)))
        ancho, alto = abs(x1 - x0), abs(y1 - y0)
        if ancho <= 0 or alto <= 0:
            continue
        try:
            idef = dxf.add_image_def(filename=f"{carpeta_img.name}/{ruta.name}",
                                     size_in_pixel=(ancho_px, alto_px))
            msp.add_image(image_def=idef, insert=(x0, y0),
                          size_in_units=(ancho, alto),
                          dxfattribs={"layer": CAPA_IMG})
            n += 1
        except Exception:
            continue
    return n


def es_circulo(pts, tol=0.02):
    """Si los puntos describen una circunferencia, devuelve (centro, radio).

    Dos detalles que costaron encontrarlos:

    1. El centro se toma de la CAJA, no promediando vertices. El contorno
       cerrado repite el primer punto al final y ese duplicado desplaza el
       promedio lo justo para que ningun circulo pase la prueba.

    2. Estos PDF no traen ni una sola curva bezier: Revit exporta los
       circulos como poligonos de 20-40 lados. Por eso la deteccion mira la
       forma del poligono y no el tipo de operador.

    Detectarlos importa porque un CIRCLE de verdad se puede acotar, escalar
    y editar como circulo; una polilinea de 24 lados no.
    """
    if len(pts) < 10:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ancho, alto = max(xs) - min(xs), max(ys) - min(ys)
    if ancho <= 0 or alto <= 0:
        return None
    if not (0.95 < ancho / alto < 1.05):        # debe ser redondo, no ovalado
        return None
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    radios = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    r = sum(radios) / len(radios)
    if r <= 0 or (max(radios) - min(radios)) / r > tol:
        return None
    if dist(pts[0], pts[-1]) > 0.1 * r:          # tiene que cerrar
        return None
    return (cx, cy), r


def caja(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def area_firmada(pts):
    """Area con signo (formula del zapatero). El signo da la orientacion."""
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def agrupar_huecos(lista):
    """Agrupa contornos de relleno en [exterior, hueco, hueco...].

    Un contorno contenido en otro es hueco solo si:
      - el camino usa la regla par-impar (even-odd), o
      - su orientacion es contraria a la del exterior (regla nonzero).

    Esta es la regla del propio PDF, y hubo que llegar a ella por descarte.
    Agrupar todos los contornos de un camino borraba la trama de cubierta
    (decenas de bandas disjuntas que la regla par-impar alternaba). Usar solo
    la caja contenedora hacia lo mismo: las bandas caen dentro del rectangulo
    de fondo sin ser huecos suyos.

    El caso que esto resuelve: el globo de eje son dos circulos concentricos
    formando un anillo; rellenados por separado dan un disco negro que tapa
    la letra del eje.
    """
    restantes = sorted(lista, key=lambda t: -((caja(t.pts)[2] - caja(t.pts)[0])
                                              * (caja(t.pts)[3] - caja(t.pts)[1])))
    grupos = []
    while restantes:
        externo = restantes.pop(0)
        ex0, ey0, ex1, ey1 = caja(externo.pts)
        grupo = [externo]
        quedan = []
        signo_ext = area_firmada(externo.pts) >= 0
        for t in restantes:
            x0, y0, x1, y1 = caja(t.pts)
            dentro = (x0 >= ex0 and y0 >= ey0 and x1 <= ex1 and y1 <= ey1)
            opuesto = (area_firmada(t.pts) >= 0) != signo_ext
            if dentro and (t.par_impar or opuesto):
                grupo.append(t)
            else:
                quedan.append(t)
        restantes = quedan
        grupos.append(grupo)
    return grupos


# Modo de capas, espejo de la opcion del dialogo de AutoCAD:
#   "tipo"  -> PDF_Geometry / PDF_Text / PDF_Solid Fills  (lo que hace la
#              opcion "crear capas de objeto", y lo que trae el DWG de
#              accoreconsole)
#   "color" -> una capa por color del objeto
#   "una"   -> todo en la capa 0
# Se aceptan los nombres en ingles y en espanol; internamente se usa uno.
ALIAS_CAPAS = {"type": "tipo", "tipo": "tipo",
               "color": "color", "colour": "color",
               "single": "una", "una": "una"}
MODO_CAPAS = set(ALIAS_CAPAS.values())
_modo_capas = "tipo"


def capa_de(trazo, capa_por_tipo):
    if _modo_capas == "una":
        return "0"
    if _modo_capas == "color":
        if es_negro(trazo.color):
            return "PDF_Color_Negro"
        r, g, b = (int(round(c * 255)) for c in trazo.color)
        return "PDF_Color_%d_%d_%d" % (r, g, b)
    return capa_por_tipo


# -------------------------------------------------------------------- escribir

def convertir(ruta_pdf, ruta_dxf, unir=True, con_texto=True,
              con_imagenes=True, con_rellenos=True, capas="tipo",
              sin_mascaras=False, con_arcos=False, binario=False,
              pagina_num=0):
    """Opciones espejo del dialogo Importar PDF de AutoCAD:
        unir          -> unir segmentos de linea y arco contiguos
        con_rellenos  -> importar rellenos solidos
        con_imagenes  -> importar imagenes raster
        con_texto     -> importar texto (siempre editable; el reconocimiento
                         SHX no aplica, el texto ya trae fuentes embebidas)
        capas         -> "tipo" | "color" | "una"
        sin_mascaras  -> descartar los rellenos blancos de fondo de texto
                         (invisibles en el PDF; AutoCAD si los importa)
        con_arcos     -> reconstruir arcos ademas de circulos. Desactivado
                         por defecto: los arcos de AutoCAD son redondeos de
                         esquina diminutos (radio mediano 0.001"), mientras
                         que la deteccion por forma convierte tambien
                         cadenas medianas que el deja como polilinea. Una
                         polilinea se ve igual y no inventa geometria.
    """
    global _modo_capas
    capas = ALIAS_CAPAS.get(str(capas).lower())
    if capas is None:
        raise ValueError("layers must be one of: %s"
                         % ", ".join(sorted(ALIAS_CAPAS)))
    _modo_capas = capas
    t0 = time.time()
    ruta_pdf, ruta_dxf = Path(ruta_pdf), Path(ruta_dxf)
    doc_pdfium = pdfium.PdfDocument(str(ruta_pdf))
    pagina_pdfium = doc_pdfium[pagina_num]
    crop_x0, crop_y0, crop_x1, crop_y1 = pagina_pdfium.get_cropbox()
    conv = Lienzo(crop_y1 - crop_y0)

    # setup=False: con setup=True ezdxf mete 30 estilos de texto propios
    # (Liberation, OpenSans...) que AutoCAD no crea. La importacion de
    # AutoCAD deja solo Standard y los estilos PDF que hagan falta.
    dxf = ezdxf.new("R2018", setup=False)
    dxf.header["$INSUNITS"] = 4        # milimetros, como declara AutoCAD
    dxf.styles.get("Standard").dxf.font = "arial.ttf"   # AutoCAD lo deja asi
    msp = dxf.modelspace()
    for capa in (CAPA_GEOM, CAPA_TEXTO, CAPA_RELL, CAPA_IMG):
        if capa not in dxf.layers:
            dxf.layers.add(capa)

    trazos = extraer_trazos(pagina_pdfium, conv)
    fragmentos_texto = extraer_texto(pagina_pdfium, conv) if con_texto else []
    brutos = len(trazos)
    if unir:
        trazos = unir_trazos(trazos)

    dom_geom = color_dominante(trazos, relleno=False)
    dom_rell = color_dominante(trazos, relleno=True)
    for capa, dom in ((CAPA_GEOM, dom_geom), (CAPA_RELL, dom_rell)):
        if dom is not None and capa in dxf.layers:
            dxf.layers.get(capa).rgb = rgb255(dom)

    n_poli = n_hatch = n_circ = n_arco = n_masc = 0
    rellenos = {}
    orden_dibujo = []
    pendientes = []          # (orden, funcion que escribe la entidad)
    for t in trazos:
        if len(t.pts) < 2:
            continue
        if t.relleno and len(t.pts) >= 3:
            if not con_rellenos:
                continue
            if sin_mascaras and es_blanco(t.color):
                n_masc += 1
                continue
            rellenos.setdefault((t.grupo, t.color), []).append(t)
        else:
            capa = capa_de(t, CAPA_GEOM)
            if capa not in dxf.layers:
                dxf.layers.add(capa)
            attr = {"layer": capa, "lineweight": t.grosor}
            attr.update(atributos_color(t.color, dom_geom))
            arco = None if (t.circulo or not con_arcos) else es_arco(t.pts)

            def escribe_trazo(t=t, attr=attr, arco=arco):
                if t.circulo:
                    centro, radio = t.circulo
                    return msp.add_circle(centro, radio, dxfattribs=attr), "c"
                if arco:
                    centro, radio, a0, a1 = arco
                    return msp.add_arc(centro, radio, a0, a1,
                                       dxfattribs=attr), "a"
                return msp.add_lwpolyline(
                    t.pts, close=t.cerrado,
                    dxfattribs=dict(attr, const_width=0.0)), "p"

            pendientes.append((t.orden, escribe_trazo))

    for (_, color), lista in rellenos.items():
        for contornos in agrupar_huecos(lista):
            capa_h = capa_de(contornos[0], CAPA_RELL)
            if capa_h not in dxf.layers:
                dxf.layers.add(capa_h)

            def escribe_relleno(contornos=contornos, color=color,
                                capa_h=capa_h):
                if es_negro(color):
                    h = msp.add_hatch(color=7, dxfattribs={"layer": capa_h})
                elif color == dom_rell:
                    h = msp.add_hatch(color=256, dxfattribs={"layer": capa_h})
                else:
                    h = msp.add_hatch(color=256, dxfattribs={"layer": capa_h})
                    h.rgb = rgb255(color)
                if len(contornos) > 1:
                    h.dxf.hatch_style = 0
                # AutoCAD deja TODOS los rellenos importados al 50% de
                # transparencia (alfa 127, 0x0200007F). No es un detalle
                # cosmetico: es lo que permite ver la trama por debajo de
                # las mascaras de fondo de texto en vez de un bloque opaco.
                h.dxf.transparency = TRANSPARENCIA_RELLENO
                for c in contornos:
                    h.paths.add_polyline_path([(p[0], p[1]) for p in c.pts],
                                              is_closed=True)
                return h, "h"

            pendientes.append((min(c.orden for c in contornos),
                               escribe_relleno))

    # UNA sola pasada, en el orden en que el PDF pinta. El orden de la base
    # de datos vale por si AutoCAD no aplica la tabla de ordenacion.
    pendientes.sort(key=lambda x: x[0])
    for orden, escribir in pendientes:
        ent, clase = escribir()
        orden_dibujo.append((ent.dxf.handle, orden))
        if clase == "p":
            n_poli += 1
        elif clase == "c":
            n_circ += 1
        elif clase == "a":
            n_arco += 1
        else:
            n_hatch += 1

    n_txt = 0
    n_ajustados = [0]
    if con_texto:
        cache = set()
        for f in fragmentos_texto:
            estilo, cap, _ttf = estilo_para(dxf, f["fuente"], cache)
            alto = f["escala_vertical"] / PUNTOS_POR_PULGADA * cap
            # Tz viene directamente de las dos columnas de la matriz PDF;
            # este margen solo evita ensuciar el DXF con un \W cosmetico
            # cuando la escala es practicamente 1, no filtra ruido medido.
            corregir_ancho = abs(f["tz"] - 1.0) > 0.005
            attr = {
                "layer": "0" if _modo_capas == "una" else CAPA_TEXTO,
                "style": estilo,
                "char_height": alto,
                "rotation": f["rot"],
                "attachment_point": 7,      # abajo-izquierda, como AutoCAD
                # los cuatro de abajo son los valores que AutoCAD escribe
                # explicitamente en cada MTEXT importado
                "width": 0.0,               # sin ajuste de linea
                "defined_height": 0.0,
                "line_spacing_style": 1,
                "line_spacing_factor": 1.0,
                "flow_direction": 5,
            }
            if f["color"] <= 0x1F1F1F:
                attr["color"] = 7
            else:
                attr["color"] = 256
                attr["true_color"] = f["color"]
            # AutoCAD ancla el MTEXT abajo-izquierda, un 1.7% de la altura
            # por debajo de la linea base que da el PDF (medido comparando
            # 441 textos contra su importacion).
            x, y = f["ins"]
            attr["insert"] = (x, y - 0.017 * alto)
            cuerpo = escapa_mtext(f["texto"])
            if corregir_ancho:
                # \W es el codigo de MTEXT para el factor de anchura
                cuerpo = "\\W%.4f;%s" % (f["tz"], cuerpo)
                n_ajustados[0] += 1
            t_ent = msp.add_mtext(cuerpo, dxfattribs=attr)
            # el texto siempre al frente
            orden_dibujo.append((t_ent.dxf.handle, 10 ** 9 + n_txt))
            n_txt += 1

    n_img = 0
    if con_imagenes:
        n_img = extraer_imagenes(pagina_pdfium, conv, dxf, msp,
                                 ruta_dxf.parent / "PDF Images", ruta_dxf.name)

    # --- Zoom extension al abrir ---------------------------------------
    #
    # Sin esto el DXF sale con $EXTMIN/$EXTMAX en su valor centinela (1e20)
    # y la vista guardada en el origen con altura 1000, asi que el plano
    # abre descuadrado y hay que hacer ZOOM E a mano cada vez. AutoCAD
    # guarda la extension real y centra la vista en ella.
    xs, ys = [], []
    for t in trazos:
        for q in t.pts:
            xs.append(q[0])
            ys.append(q[1])
    if xs:
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        # Hay que fijarlo en el LAYOUT, no en la cabecera: al guardar,
        # ezdxf reescribe $EXTMIN/$EXTMAX copiandolos de msp.dxf.extmin.
        msp.dxf.extmin = (x0, y0, 0.0)
        msp.dxf.extmax = (x1, y1, 0.0)
        dxf.header["$EXTMIN"] = (x0, y0, 0.0)
        dxf.header["$EXTMAX"] = (x1, y1, 0.0)
        margen = 1.0074                      # el mismo aire que deja AutoCAD
        alto = max((y1 - y0), (x1 - x0)) * margen
        dxf.set_modelspace_vport(height=alto,
                                 center=((x0 + x1) / 2, (y0 + y1) / 2))

    # Tabla de orden de dibujo (SORTENTSTABLE).
    #
    # Sin ella AutoCAD dibuja los rellenos ENCIMA del texto aunque el texto
    # se haya creado despues: el orden por handle no manda. El efecto era
    # que las mascaras blancas de fondo tapaban las etiquetas que debian
    # proteger. AutoCAD escribe esta tabla al importar, y por eso sus DWG
    # muestran el sombreado detras del texto.
    # Los handles de ordenacion tienen que salir del mismo deposito que los
    # de las entidades. Numerarlos 1,2,3... los hace chocar con handles
    # reales y AutoCAD acaba ignorando la tabla: las mascaras blancas
    # volvian a quedar encima del texto.
    orden_dibujo.sort(key=lambda x: x[1])
    msp.set_redraw_order([(h, dxf.entitydb.next_handle())
                          for h, _ in orden_dibujo])

    if binario:
        # DXF binario: mismo contenido, sin el coste de escribirlo en texto.
        # Medido: la mitad que el DXF de texto, aun asi 4-5 veces un DWG.
        # AutoCAD lo abre igual, pero no es tan universal fuera de el.
        dxf.saveas(ruta_dxf, fmt="bin")
    else:
        dxf.saveas(ruta_dxf)
    pagina_pdfium.close()
    doc_pdfium.close()
    return {
        "trazos_brutos": brutos,
        "polilineas": n_poli,
        "circulos": n_circ,
        "arcos": n_arco,
        "mascaras_descartadas": n_masc,
        "hatches": n_hatch,
        "textos": n_txt,
        "texto_ajustado": n_ajustados[0],
        "imagenes": n_img,
        "total": n_poli + n_circ + n_arco + n_hatch + n_txt + n_img,
        "segundos": round(time.time() - t0, 1),
        "hoja": (round((crop_x1 - crop_x0) / 72, 2),
                 round((crop_y1 - crop_y0) / 72, 2)),
    }


# --------------------------------------------------------------------- DWG

RUTAS_ODA = [
    r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files\ODA\*\ODAFileConverter.exe",
    "/usr/bin/ODAFileConverter",
    "/opt/oda/ODAFileConverter",
]


def busca_oda():
    """Localiza ODA File Converter, si esta instalado.

    Es gratuito pero propietario, asi que no se puede incluir en este
    repositorio: se instala aparte desde la web de Open Design Alliance.
    Sin el, la salida se queda en DXF, que AutoCAD y cualquier CAD abren
    igual -- DWG es formato cerrado y no hay libreria abierta que lo
    escriba de forma fiable.
    """
    import glob
    import shutil
    encontrado = shutil.which("ODAFileConverter")
    if encontrado:
        return encontrado
    for patron in RUTAS_ODA:
        for c in sorted(glob.glob(patron), reverse=True):
            if os.path.isfile(c):
                return c
    return None


def a_dwg(carpeta_dxf, carpeta_dwg=None, version="ACAD2018", oda=None):
    """Convierte a DWG los DXF de una carpeta, con ODA File Converter."""
    import subprocess
    oda = oda or busca_oda()
    if not oda:
        return None
    carpeta_dxf = Path(carpeta_dxf)
    carpeta_dwg = Path(carpeta_dwg or (carpeta_dxf / "DWG"))
    carpeta_dwg.mkdir(parents=True, exist_ok=True)
    # ODAFileConverter <entrada> <salida> <version> <tipo> <recursivo> <audit>
    subprocess.run([oda, str(carpeta_dxf), str(carpeta_dwg),
                    version, "DWG", "0", "1", "*.DXF"],
                   check=False)
    return sorted(carpeta_dwg.glob("*.dwg"))


def informe(nombre, r):
    print(f"  {nombre}")
    print(f"     sheet {r['hoja'][0]} x {r['hoja'][1]} in | "
          f"raw {r['trazos_brutos']} -> poly {r['polilineas']}, "
          f"circ {r['circulos']}, arc {r['arcos']}, hatch {r['hatches']}, "
          f"masks dropped {r['mascaras_descartadas']}, ")
    print(f"     text {r['textos']} ({r['texto_ajustado']} width-corrected), "
          f"img {r['imagenes']}")
    print(f"     TOTAL {r['total']} entities in {r['segundos']}s")


def bandera(*nombres):
    """True si cualquiera de los alias aparece en la linea de comandos."""
    return any(n in sys.argv for n in nombres)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1

    capas = "tipo"
    for a in sys.argv:
        if a.startswith("--layers=") or a.startswith("--capas="):
            capas = a.split("=", 1)[1]

    opciones = dict(
        unir=not bandera("--no-join", "--sin-unir"),
        con_texto=not bandera("--no-text", "--sin-texto"),
        con_imagenes=not bandera("--no-images", "--sin-imagenes"),
        con_rellenos=not bandera("--no-fills", "--sin-rellenos"),
        sin_mascaras=bandera("--no-masks", "--sin-mascaras"),
        con_arcos=bandera("--arcs", "--arcos"),
        binario=bandera("--binary", "--binario"),
        capas=capas,
    )

    origen = Path(args[0])
    if origen.is_dir() or bandera("--batch", "--lote"):
        salida = Path(args[1]) if len(args) > 1 else origen / "DXF"
        salida.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        for pdf in sorted(origen.glob("*.pdf")):
            informe(pdf.name, convertir(pdf, salida / (pdf.stem + ".dxf"),
                                        **opciones))
        print(f"\n  batch done in {time.time()-t0:.1f}s -> {salida}")
        if "--dwg" in sys.argv:
            hechos = a_dwg(salida)
            if hechos is None:
                print("  --dwg: ODA File Converter not found (optional, free"
                      " download). The DXF files are ready to use.")
            else:
                print(f"  --dwg: {len(hechos)} DWG in {salida / 'DWG'}")
    else:
        destino = Path(args[1]) if len(args) > 1 else origen.with_suffix(".dxf")
        informe(origen.name, convertir(origen, destino, **opciones))
        print(f"     -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
