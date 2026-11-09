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


def _vaciar(hoja, rango: str, conservar: frozenset[str] = frozenset()) -> None:
    c0, f0, c1, f1 = range_boundaries(rango)
    for fila in hoja.iter_rows(min_row=f0, max_row=f1, min_col=c0, max_col=c1):
        for celda in fila:
            if isinstance(celda, MergedCell) or celda.coordinate in conservar:
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
    conservar = frozenset(libro_decl.conservar)
    for rango in libro_decl.vaciar:
        _vaciar(hoja, rango, conservar)

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

    if libro_decl.celda_paciente:
        # el nombre lo escribe la usuaria (al subir la foto o al revisar); va tal cual
        hoja[libro_decl.celda_paciente].value = ev.paciente or None

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


def proponer_conservar(base: Path, hoja: str | None, celdas: list[str]) -> list[str]:
    """Celdas que quedan dentro del rectángulo de los ítems pero no son datos: textos fijos de la
    hoja de la usuaria (p. ej. la letra A, B o C que marca el final de cada columna). Se conservan
    al vaciar; los valores del paciente son números y esos sí se limpian."""
    if not celdas:
        return []
    try:
        libro = load_workbook(base)
    except (OSError, ValueError, KeyError, BadZipFile) as e:
        raise LibroBaseInvalido(f"No se pudo abrir el libro de Excel «{base.name}»: {e}") from e
    if hoja and hoja not in libro.sheetnames:
        raise LibroBaseInvalido(f"El libro no tiene la hoja «{hoja}».")
    ws = libro[hoja] if hoja else libro.worksheets[0]
    limites = [range_boundaries(c) for c in celdas]
    c0, f0 = min(b[0] for b in limites), min(b[1] for b in limites)
    c1, f1 = max(b[2] for b in limites), max(b[3] for b in limites)
    mias = set(celdas)
    return [
        c.coordinate
        for fila in ws.iter_rows(min_row=f0, max_row=f1, min_col=c0, max_col=c1)
        for c in fila
        if isinstance(c.value, str)
        and c.value.strip()
        and not c.value.startswith("=")
        and c.coordinate not in mias
    ]


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


def comprobar_libro(base: Path, hoja: str | None, items: list[tuple[str, str | None]]) -> dict:
    """Cruza la plantilla con el libro de la usuaria. `items` son `(rótulo, celda|None)`.

    El libro sabe cuántos datos espera su hoja; la foto, dónde están. Si no cuadran, lo más
    probable es que el reconocimiento haya perdido filas o que una celda esté mal asignada. Solo
    avisa: la decisión es de la usuaria. Devuelve conteos, listas cortas y `avisos` en palabras."""
    try:
        libro = load_workbook(base)
    except (OSError, ValueError, KeyError, BadZipFile) as e:
        raise LibroBaseInvalido(f"No se pudo abrir el libro de Excel «{base.name}»: {e}") from e
    if hoja and hoja not in libro.sheetnames:
        raise LibroBaseInvalido(f"El libro no tiene la hoja «{hoja}».")
    ws = libro[hoja] if hoja else libro.worksheets[0]

    sin_celda = [r for r, c in items if not c]
    celdas = [c for _, c in items if c]
    ocupadas: list[str] = []
    for c in celdas:
        v = ws[c].value
        if isinstance(v, str) and v.strip() and not v.strip().lstrip("-").isdigit():
            ocupadas.append(c)  # fórmula o rótulo: escribir encima lo destruiría
    numeros_sin_item: list[str] = []
    numeros_en_area = 0
    if celdas:
        limites = [range_boundaries(c) for c in celdas]
        c0, f0 = min(b[0] for b in limites), min(b[1] for b in limites)
        c1, f1 = max(b[2] for b in limites), max(b[3] for b in limites)
        mias = set(celdas)
        for fila in ws.iter_rows(min_row=f0, max_row=f1, min_col=c0, max_col=c1):
            for c in fila:
                if isinstance(c.value, bool) or not isinstance(c.value, int | float):
                    continue
                numeros_en_area += 1
                if c.coordinate not in mias:
                    numeros_sin_item.append(c.coordinate)

    def lista(xs: list[str], tope: int = 6) -> str:
        return ", ".join(xs[:tope]) + (f" y {len(xs) - tope} más" if len(xs) > tope else "")

    avisos: list[str] = []
    if sin_celda:
        avisos.append(
            f"{len(sin_celda)} ítem(s) no tienen celda en el libro y no se escribirán: {lista(sin_celda)}."
        )
    if ocupadas:
        avisos.append(
            f"{len(ocupadas)} ítem(s) apuntan a celdas con fórmula o texto fijo ({lista(ocupadas)}): "
            "se sobrescribirían. Revisa su celda."
        )
    if numeros_sin_item:
        avisos.append(
            f"El libro tiene {len(numeros_sin_item)} celda(s) con número dentro del área de datos que "
            f"ningún ítem usa ({lista(numeros_sin_item)}): quizá la plantilla perdió filas."
        )
    if not avisos:
        avisos.append(
            f"El libro y la plantilla cuadran: {len(celdas)} ítems, cada uno con su celda."
        )
    return {
        "items": len(items),
        "con_celda": len(celdas),
        "sin_celda": len(sin_celda),
        "ocupadas": ocupadas,
        "numeros_sin_item": numeros_sin_item,
        "numeros_en_area": numeros_en_area,
        "cuadra": not (sin_celda or ocupadas or numeros_sin_item),
        "avisos": avisos,
    }
