# Verificacion final: se eliminaron los falsos positivos de estiramiento

Se compararon los MTEXT de `pdf2dxf.py` contra PDFIMPORT de AutoCAD en los tres planos de `referencias/`. Los planos son confidenciales: esta nota es local al repositorio y no reproduce ni publica su contenido.

## Criterio aplicado

La correccion de ancho ahora se limita a `0 < fac < 0.95`. La medicion independiente de la matriz de texto con PDFium confirmo Tz distinto de 1 en 256/256 spans con `fac < 1`, y Tz = 1 en 9/9 spans con `fac > 1`: estos ultimos son ruido entre las metricas del subset embebido y Arial, no estiramiento del PDF.

El emparejado es 1:1 por texto plano y posicion de insercion; suma `0.017 * char_height` a la coordenada y del motor para compensar su offset de linea base. La tolerancia es la distancia maxima de los pares preliminares que ya coinciden en altura (2%).

| Plano | Pares dentro de 2% | Fuera | Corregidos antes | Corregidos finales | Sin correccion, cambio maximo de alto |
| --- | ---: | ---: | ---: | ---: | ---: |
| A-01 | 436 / 436 | 0 | 200 | 192 | 0.000000% |
| A-02 | 249 / 249 | 0 | 81 | 80 | 0.000000% |
| A-06 | 841 / 841 | 0 | 143 | 140 | 0.000000% |
| **Total** | **1,526 / 1,526** | **0** | **424** | **412** | **0.000000%** |

Los contadores finales de `\\W` bajan respecto a los previos porque se retiraron los falsos positivos: 8 en A01, 1 en A02 y 3 en A06 (12 ocurrencias en la salida). Por ello no se cumplen literalmente los conteos solicitados de 200/81/143; conservarlos seria incompatible con no emitir `\\W` para los spans con `fac > 1`. Los textos citados no conservan `\\W`: A01 encontro 7 ocurrencias y 0 con `\\W`; A02, 0 y 0; A06, 2 y 0.

## Salida real

```text
python spike/verifica_alturas.py --etapa despues --sin-convertir --plano A-01 --verificar-invariantes
ALTURAS DESPUES (tolerancia: 2%)
A-01: 436/436 dentro de 2%; 0 fuera; peor=0.07% | "J1'": AutoCAD=4.30 pt, motor=4.30 pt; d=0.0010
  distancia (pares ya dentro): n=436, min=0.0000, p50=0.0010, p90=0.0026, p95=0.0118, p99=0.0202, max=0.0488; tolerancia=0.0488
  sin pareja por posicion: AutoCAD=5, motor=10
  clases sin pareja: AutoCAD texto-inexistente=5, texto-lejano=0; motor texto-inexistente=9, texto-lejano=1
  ejemplo sin pareja AutoCAD: 'NPT NIVEL DE PISO TERMINADO' @ (21.5372, 33.6464)
  ejemplo sin pareja motor: 'NPT' @ (21.5372, 33.6464)
  invariantes: 192 corregidos, max |alto*\W|=0.015065%; 246 sin comprimir, max |alto|=0.000000%

python spike/verifica_alturas.py --etapa despues --sin-convertir --plano A-02 --verificar-invariantes
ALTURAS DESPUES (tolerancia: 2%)
A-02: 249/249 dentro de 2%; 0 fuera; peor=0.05% | "35'": AutoCAD=4.30 pt, motor=4.30 pt; d=0.0011
  distancia (pares ya dentro): n=249, min=0.0000, p50=0.0010, p90=0.0032, p95=0.0050, p99=0.0243, max=0.0488; tolerancia=0.0488
  sin pareja por posicion: AutoCAD=3, motor=6
  clases sin pareja: AutoCAD texto-inexistente=3, texto-lejano=0; motor texto-inexistente=6, texto-lejano=0
  ejemplo sin pareja AutoCAD: 'METROS ING. <nombre>' @ (17.4111, 0.5021)
  ejemplo sin pareja motor: 'METROS' @ (17.4111, 0.5185)
  invariantes: 80 corregidos, max |alto*\W|=0.015065%; 174 sin comprimir, max |alto|=0.000000%

python spike/verifica_alturas.py --etapa despues --sin-convertir --plano A-06 --verificar-invariantes
ALTURAS DESPUES (tolerancia: 2%)
A-06: 841/841 dentro de 2%; 0 fuera; peor=0.07% | "J1'": AutoCAD=4.30 pt, motor=4.30 pt; d=0.0010
  distancia (pares ya dentro): n=841, min=0.0000, p50=0.0010, p90=0.0022, p95=0.0032, p99=0.0050, max=0.0488; tolerancia=0.0488
  sin pareja por posicion: AutoCAD=38, motor=58
  clases sin pareja: AutoCAD texto-inexistente=36, texto-lejano=2; motor texto-inexistente=38, texto-lejano=20
  ejemplo sin pareja AutoCAD: 'ESC: 1 : 5' @ (7.1436, 13.8607)
  ejemplo sin pareja motor: 'BAP' @ (23.7095, 21.9646)
  invariantes: 140 corregidos, max |alto*\W|=0.015056%; 756 sin comprimir, max |alto|=0.000000%
```
