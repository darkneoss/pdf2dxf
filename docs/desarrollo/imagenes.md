# Verificacion de imagenes por lote

Comando ejecutado desde la raiz del repositorio:

```text
python pdf2dxf.py referencias spike\test_img --batch
python pdf2dxf.py referencias\A-03.pdf spike\solo_img\A-03.dxf
python spike\verifica_imagenes.py spike\test_img spike\solo_img
```

Salida real de `verifica_imagenes.py`:

```text
PNG: 376
A-03: 375 IMAGE existentes, sin logo de B-01
B-01: 1 IMAGE existente, logo 97x222
Referencias PNG compartidas entre DXF: 0
Auditor ezdxf: 0 errores en todos los DXF
A-03 lote vs individual: PNG identicos
```
