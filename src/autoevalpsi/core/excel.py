"""CO-R6: exportador Excel.

Decisiones aprobadas (2026-11-06):

- **CO-D1 a)**: un `.xlsx` por evaluación con la forma del papel (hoja «Evaluación») y un
  consolidado por formulario (`consolidado_<id de plantilla>.xlsx`, hoja «Consolidado»): una fila
  por evaluación, una columna por ítem con la opción elegida.
- **CO-D2 a)**: nombre `AAAA-MM-DD_<formulario>_<paciente>.xlsx`, saneado (CO-07); con
  `NombreArchivo.INICIALES` el paciente se reduce a sus iniciales. Solo cambia el nombre del
  archivo: el contenido lleva el nombre completo.

Contrato público: la forma de las dos hojas (columnas y orden) es el formato del Excel.

Reglas:

- Reexportar la misma evaluación (misma `Evaluacion.id`) sobrescribe su archivo y reemplaza su fila
  del consolidado: nunca duplica. El id viaja en las propiedades del libro (`identifier`).
  Otra evaluación con el mismo nombre de archivo recibe un sufijo « (2)», « (3)»...
- Se escribe a un temporal y se reemplaza el destino (CO-08): si Excel tiene el archivo abierto,
  Windows rechaza el reemplazo y se lanza `ArchivoBloqueado`; el archivo anterior queda intacto.
  `exportar` guarda primero el de la evaluación; si el consolidado está bloqueado, la evaluación ya
  está a salvo y basta reintentar `actualizar_consolidado` (idempotente).
- Un texto que empieza por `=` se guarda como texto, nunca como fórmula.
"""

import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.cell import Cell
from openpyxl.drawing.image import Image as ImagenExcel
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from autoevalpsi.core.plantilla import Plantilla

HOJA_EVALUACION = "Evaluación"
HOJA_CONSOLIDADO = "Consolidado"
MARCA = "X"
COLUMNAS_FIJAS_CONSOLIDADO = ("ID evaluación", "Fecha", "Paciente", "Versión plantilla")

_ALTO_RECORTE_PX = 60
_NEGRITA = Font(bold=True)
_ENCABEZADO = PatternFill("solid", fgColor="E7E6E6")
_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
               *(f"LPT{i}" for i in range(1, 10))}  # fmt: skip
_MAX_COMPONENTE = 60


class NombreArchivo(StrEnum):
    PACIENTE = "paciente"
    INICIALES = "iniciales"


class ArchivoBloqueado(Exception):
    """No se pudo escribir el archivo (CO-08): casi siempre está abierto en Excel."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        super().__init__(
            f"No se pudo guardar «{ruta.name}». Si está abierto en Excel, ciérralo y vuelve a "
            "intentar; la evaluación no se perdió."
        )


@dataclass(frozen=True)
class FilaEvaluacion:
    item: int
    opcion: str | None  # texto de la opción elegida; None = sin respuesta
    observacion: str = ""
    revisado: bool = False
    recorte: np.ndarray | None = None  # imagen (BGR o gris) de la observación manuscrita


@dataclass(frozen=True)
class Evaluacion:
    id: str  # clave estable: reexportar con el mismo id no duplica
    plantilla: Plantilla
    fecha: date
    paciente: str
    filas: tuple[FilaEvaluacion, ...]
    cabecera: dict[str, str] = field(default_factory=dict)  # campos extra de la cabecera

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("la evaluación necesita un id")
        validos = {f.item: t.opciones for p in self.plantilla.paginas for t in p.tablas
                   for f in t.filas}  # fmt: skip
        vistos: set[int] = set()
        for f in self.filas:
            if f.item not in validos:
                raise ValueError(f"el ítem {f.item} no existe en la plantilla {self.plantilla.id}")
            if f.item in vistos:
                raise ValueError(f"el ítem {f.item} viene repetido")
            vistos.add(f.item)
            if f.opcion is not None and f.opcion not in validos[f.item]:
                raise ValueError(
                    f"ítem {f.item}: «{f.opcion}» no es una opción válida {validos[f.item]}"
                )


@dataclass(frozen=True)
class ResultadoExportacion:
    evaluacion: Path
    consolidado: Path


# --- nombres de archivo (CO-07) -------------------------------------------------------------


def sanear_nombre(texto: str, vacio: str = "sin-nombre") -> str:
    """Texto apto como componente de nombre de archivo de Windows (conserva tildes y ñ)."""
    t = unicodedata.normalize("NFC", texto)
    t = re.sub(r'[\x00-\x1f<>:"/\\|?*]', " ", t)
    t = re.sub(r"\s+", "_", t.strip())
    t = t.strip("._")[:_MAX_COMPONENTE].strip("._")
    if not t:
        return vacio
    if t.split(".")[0].upper() in _RESERVADOS:
        t = f"_{t}"
    return t


def iniciales(nombre: str) -> str:
    palabras = re.findall(r"[^\W\d_]+", unicodedata.normalize("NFC", nombre))
    return "".join(p[0].upper() for p in palabras) or "sin-nombre"


def nombre_archivo(ev: Evaluacion, modo: NombreArchivo = NombreArchivo.PACIENTE) -> str:
    paciente = iniciales(ev.paciente) if modo == NombreArchivo.INICIALES else ev.paciente
    return f"{ev.fecha.isoformat()}_{sanear_nombre(ev.plantilla.id)}_{sanear_nombre(paciente)}.xlsx"


# --- utilidades de escritura ----------------------------------------------------------------


def _texto(celda: Cell, valor: str) -> None:
    celda.value = valor
    if valor.startswith("="):
        celda.data_type = "s"  # nunca fórmula


def _guardar(libro: Workbook, destino: Path) -> None:
    """Escribe a un temporal y reemplaza el destino; el anterior queda intacto si falla."""
    temporal = destino.with_name(f".{destino.name}.tmp")
    try:
        libro.save(temporal)
        os.replace(temporal, destino)
    except PermissionError as e:
        temporal.unlink(missing_ok=True)
        raise ArchivoBloqueado(destino) from e


def _id_guardado(ruta: Path) -> str | None:
    try:
        libro = load_workbook(ruta, read_only=True)
    except PermissionError as e:
        raise ArchivoBloqueado(ruta) from e
    except Exception:  # noqa: BLE001 - archivo ajeno o dañado: no es el nuestro
        return None
    try:
        return libro.properties.identifier
    finally:
        libro.close()


def _ruta_libre(carpeta: Path, nombre: str, evaluacion_id: str) -> Path:
    """`nombre` en `carpeta`; si lo ocupa otra evaluación, añade « (2)», « (3)»..."""
    base = Path(nombre)
    n = 1
    while True:
        ruta = carpeta / (nombre if n == 1 else f"{base.stem} ({n}){base.suffix}")
        if not ruta.exists() or _id_guardado(ruta) == evaluacion_id:
            return ruta
        n += 1


def _png(recorte: np.ndarray) -> tuple[BytesIO, int, int]:
    alto, ancho = recorte.shape[:2]
    escala = min(1.0, _ALTO_RECORTE_PX / alto)
    if escala < 1.0:
        recorte = cv2.resize(recorte, (max(1, round(ancho * escala)), _ALTO_RECORTE_PX),
                             interpolation=cv2.INTER_AREA)  # fmt: skip
    ok, buf = cv2.imencode(".png", recorte)
    if not ok:
        raise ValueError("no se pudo codificar el recorte")
    return BytesIO(buf.tobytes()), recorte.shape[1], recorte.shape[0]


# --- archivo de la evaluación ---------------------------------------------------------------


def _hoja_evaluacion(ev: Evaluacion, incluir_recortes: bool) -> Workbook:
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None
    hoja.title = HOJA_EVALUACION
    libro.properties.identifier = ev.id
    libro.properties.title = f"{ev.plantilla.nombre} — {ev.fecha.isoformat()}"

    cabecera = [
        ("Formulario", ev.plantilla.nombre),
        ("Fecha", ev.fecha.isoformat()),
        ("Paciente", ev.paciente),
        *((k, v) for k, v in ev.cabecera.items()),
    ]
    for r, (clave, valor) in enumerate(cabecera, start=1):
        hoja.cell(r, 1, clave).font = _NEGRITA
        _texto(hoja.cell(r, 2), valor)
    fila_actual = len(cabecera) + 2

    por_item = {f.item: f for f in ev.filas}
    for tabla in (t for p in ev.plantilla.paginas for t in p.tablas):
        encabezados = ["Ítem", "Descripción", *tabla.opciones, "Observación", "Revisado"]
        col_recorte = len(encabezados) + 1 if incluir_recortes else None
        if col_recorte:
            encabezados.append("Recorte")
        for c, titulo in enumerate(encabezados, start=1):
            celda = hoja.cell(fila_actual, c, titulo)
            celda.font = _NEGRITA
            celda.fill = _ENCABEZADO
            celda.alignment = Alignment(horizontal="center", wrap_text=True)
        fila_actual += 1
        for fila in tabla.filas:
            dato = por_item.get(fila.item)
            hoja.cell(fila_actual, 1, fila.item)
            _texto(hoja.cell(fila_actual, 2), fila.texto)
            if dato and dato.opcion is not None:
                c = 3 + tabla.opciones.index(dato.opcion)
                hoja.cell(fila_actual, c, MARCA).alignment = Alignment(horizontal="center")
            c_obs = 3 + len(tabla.opciones)
            if dato and dato.observacion:
                _texto(hoja.cell(fila_actual, c_obs), dato.observacion)
            hoja.cell(fila_actual, c_obs + 1, "Sí" if dato and dato.revisado else "No")
            if col_recorte and dato and dato.recorte is not None:
                buf, ancho, alto = _png(dato.recorte)
                imagen = ImagenExcel(buf)
                imagen.width, imagen.height = ancho, alto
                hoja.add_image(imagen, f"{get_column_letter(col_recorte)}{fila_actual}")
                hoja.row_dimensions[fila_actual].height = alto * 0.75 + 4
                ancho_col = hoja.column_dimensions[get_column_letter(col_recorte)].width or 0
                hoja.column_dimensions[get_column_letter(col_recorte)].width = max(
                    ancho_col, ancho / 7 + 2
                )
            fila_actual += 1
        fila_actual += 1

    hoja.column_dimensions["A"].width = 12
    hoja.column_dimensions["B"].width = 40
    return libro


def exportar_evaluacion(
    ev: Evaluacion,
    carpeta: str | Path,
    *,
    nombre: NombreArchivo = NombreArchivo.PACIENTE,
    incluir_recortes: bool = False,
) -> Path:
    """Escribe el `.xlsx` de la evaluación en `carpeta` y devuelve su ruta."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = _ruta_libre(carpeta, nombre_archivo(ev, nombre), ev.id)
    _guardar(_hoja_evaluacion(ev, incluir_recortes), ruta)
    return ruta


# --- consolidado por formulario -------------------------------------------------------------


def ruta_consolidado(plantilla: Plantilla, carpeta: str | Path) -> Path:
    return Path(carpeta) / f"consolidado_{sanear_nombre(plantilla.id)}.xlsx"


def _columnas_item(plantilla: Plantilla) -> list[str]:
    return [f"Ítem {f.item}" for p in plantilla.paginas for t in p.tablas for f in t.filas]


def _abrir_consolidado(ruta: Path, plantilla: Plantilla) -> tuple[Workbook, Worksheet]:
    if ruta.exists():
        try:
            libro = load_workbook(ruta)
        except PermissionError as e:
            raise ArchivoBloqueado(ruta) from e
        if HOJA_CONSOLIDADO in libro.sheetnames:
            return libro, libro[HOJA_CONSOLIDADO]
        raise ValueError(f"«{ruta.name}» no es un consolidado de AutoEvalPsi")
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None
    hoja.title = HOJA_CONSOLIDADO
    for c, titulo in enumerate([*COLUMNAS_FIJAS_CONSOLIDADO, *_columnas_item(plantilla)], start=1):
        celda = hoja.cell(1, c, titulo)
        celda.font = _NEGRITA
        celda.fill = _ENCABEZADO
    hoja.freeze_panes = "E2"
    return libro, hoja


def actualizar_consolidado(ev: Evaluacion, carpeta: str | Path) -> Path:
    """Crea o amplía el consolidado del formulario; la fila de `ev.id` se reemplaza, no se repite."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = ruta_consolidado(ev.plantilla, carpeta)
    libro, hoja = _abrir_consolidado(ruta, ev.plantilla)

    columnas = {hoja.cell(1, c).value: c for c in range(1, hoja.max_column + 1)}
    for titulo in _columnas_item(ev.plantilla):  # una versión nueva de la plantilla puede traer más
        if titulo not in columnas:
            columnas[titulo] = hoja.max_column + 1
            celda = hoja.cell(1, columnas[titulo], titulo)
            celda.font = _NEGRITA
            celda.fill = _ENCABEZADO

    fila = next(
        (r for r in range(2, hoja.max_row + 1) if hoja.cell(r, 1).value == ev.id),
        max(hoja.max_row + 1, 2),
    )
    for c in range(
        1, hoja.max_column + 1
    ):  # al reemplazar, limpia los ítems de la versión anterior
        hoja.cell(fila, c).value = None
    _texto(hoja.cell(fila, columnas["ID evaluación"]), ev.id)
    hoja.cell(fila, columnas["Fecha"], ev.fecha.isoformat())
    _texto(hoja.cell(fila, columnas["Paciente"]), ev.paciente)
    hoja.cell(fila, columnas["Versión plantilla"], ev.plantilla.version)
    for f in ev.filas:
        if f.opcion is not None:
            hoja.cell(fila, columnas[f"Ítem {f.item}"], f.opcion)
    _guardar(libro, ruta)
    return ruta


def exportar(
    ev: Evaluacion,
    carpeta: str | Path,
    *,
    nombre: NombreArchivo = NombreArchivo.PACIENTE,
    incluir_recortes: bool = False,
) -> ResultadoExportacion:
    """Archivo de la evaluación + consolidado. Si el consolidado está bloqueado se lanza
    `ArchivoBloqueado` *después* de guardar el de la evaluación (CO-08)."""
    archivo = exportar_evaluacion(ev, carpeta, nombre=nombre, incluir_recortes=incluir_recortes)
    return ResultadoExportacion(archivo, actualizar_consolidado(ev, carpeta))
