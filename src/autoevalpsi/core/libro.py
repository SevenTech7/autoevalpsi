"""VD-R3: la evaluación escrita en el libro de Excel de la usuaria.

La plantilla declara un `Libro` (archivo base, hoja, rangos que se vacían) y cada ítem su `celda`.
Se abre una copia del libro, se vacían los rangos, se escribe el valor de cada ítem **tal como
quedó confirmado** (un dígito como número, una opción como texto; sin respuesta → celda vacía) y
se agrega una hoja «AutoEvalPsi» con paciente, fecha y formulario. Las fórmulas (sumas…) y el
formato del libro no se tocan: Excel las recalcula al abrir.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter, range_boundaries

HOJA_DATOS = "AutoEvalPsi"


class LibroBaseInvalido(ValueError):
    """El libro base no existe o no se puede leer; el mensaje es apto para la usuaria."""


def _valor(opcion: str) -> int | str:
    return int(opcion) if opcion.isdigit() else opcion


def _vaciar(hoja, rango: str) -> None:
    c0, f0, c1, f1 = range_boundaries(rango)
    for fila in hoja.iter_rows(min_row=f0, max_row=f1, min_col=c0, max_col=c1):
        for celda in fila:
            if isinstance(celda, MergedCell):
                continue
            if isinstance(celda.value, str) and celda.value.startswith("="):
                continue  # una fórmula nunca se borra: es el cálculo de la usuaria
            celda.value = None


def libro_de_la_usuaria(ev, base: Path) -> Workbook:
    """`ev` es un `core.excel.Evaluacion`; devuelve el libro listo para guardar."""
    libro_decl = ev.plantilla.libro
    if libro_decl is None:
        raise ValueError("la plantilla no declara un libro de Excel")
    try:
        libro = load_workbook(base)
    except (OSError, ValueError, KeyError, BadZipFile) as e:
        raise LibroBaseInvalido(
            f"No se pudo abrir el libro de Excel base «{base.name}» de la plantilla: {e}"
        ) from e
    if libro_decl.hoja and libro_decl.hoja not in libro.sheetnames:
        raise LibroBaseInvalido(f"El libro base no tiene la hoja «{libro_decl.hoja}».")
    hoja = libro[libro_decl.hoja] if libro_decl.hoja else libro.worksheets[0]
    for rango in libro_decl.vaciar:
        _vaciar(hoja, rango)

    por_item = {f.item: f for f in ev.filas}
    for pagina in ev.plantilla.paginas:
        for tabla in pagina.tablas:
            for fila in tabla.filas:
                if not fila.celda:
                    continue
                dato = por_item.get(fila.item)
                hoja[fila.celda].value = (
                    _valor(dato.opcion) if dato is not None and dato.opcion is not None else None
                )

    datos = libro.create_sheet(HOJA_DATOS)
    fecha = ev.fecha
    filas = [
        ("Paciente", ev.paciente),
        (
            "Fecha",
            fecha.strftime("%d/%m/%Y %H:%M")
            if isinstance(fecha, datetime)
            else fecha.strftime("%d/%m/%Y"),
        ),
        ("Formulario", f"{ev.plantilla.nombre} (versión {ev.plantilla.version})"),
        *[(k, v) for k, v in ev.cabecera.items()],
    ]
    for r, (k, v) in enumerate(filas, start=1):
        datos.cell(r, 1, k).font = Font(bold=True)
        datos.cell(r, 2, v)
    datos.column_dimensions["A"].width = 18
    datos.column_dimensions["B"].width = 44
    return libro


def proponer_vaciado(base: Path, hoja: str | None, celdas: list[str]) -> list[str]:
    """Rangos que se limpian antes de escribir una evaluación nueva, para que no quede nada de otro
    paciente. Siempre una **propuesta** que la usuaria revisa:

    - el rectángulo que cubren las celdas de los ítems;
    - fuera de él, los números escritos a mano (no fórmulas) y los textos cortos que están justo a
      la derecha de un número o de una fórmula (las clasificaciones «b», «mod b»).
    Los rótulos y las fórmulas nunca entran."""
    try:
        libro = load_workbook(base)
    except (OSError, ValueError, KeyError, BadZipFile) as e:
        raise LibroBaseInvalido(f"No se pudo abrir el libro de Excel «{base.name}»: {e}") from e
    if hoja and hoja not in libro.sheetnames:
        raise LibroBaseInvalido(f"El libro no tiene la hoja «{hoja}».")
    ws = libro[hoja] if hoja else libro.worksheets[0]
    propuesta: list[str] = []
    caja = None
    if celdas:
        limites = [range_boundaries(c) for c in celdas]
        c0, f0 = min(b[0] for b in limites), min(b[1] for b in limites)
        c1, f1 = max(b[2] for b in limites), max(b[3] for b in limites)
        caja = (c0, f0, c1, f1)
        propuesta.append(f"{get_column_letter(c0)}{f0}:{get_column_letter(c1)}{f1}")

    def dentro(c: int, f: int) -> bool:
        return caja is not None and caja[0] <= c <= caja[2] and caja[1] <= f <= caja[3]

    sueltas: dict[int, list[int]] = {}
    for fila in ws.iter_rows():
        for celda in fila:
            v = celda.value
            if v is None or dentro(celda.column, celda.row):
                continue
            if isinstance(v, bool):
                continue
            escrita = isinstance(v, int | float)
            if (
                not escrita
                and isinstance(v, str)
                and not v.startswith("=")
                and len(v.strip()) <= 12
            ):
                izq = ws.cell(celda.row, celda.column - 1).value if celda.column > 1 else None
                escrita = isinstance(izq, int | float) or (
                    isinstance(izq, str) and izq.startswith("=")
                )
            if escrita:
                sueltas.setdefault(celda.column, []).append(celda.row)
    for col in sorted(sueltas):
        filas = sorted(sueltas[col])
        ini = prev = filas[0]
        for f in [*filas[1:], None]:
            if f is not None and f == prev + 1:
                prev = f
                continue
            letra = get_column_letter(col)
            propuesta.append(f"{letra}{ini}" if ini == prev else f"{letra}{ini}:{letra}{prev}")
            if f is not None:
                ini = prev = f
    return propuesta
