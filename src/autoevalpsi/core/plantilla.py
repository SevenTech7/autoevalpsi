"""CO-R0: esquema versionado de plantillas de formulario y su cargador.

Contrato público (versión de esquema 1). Cambiarlo exige subir `ESQUEMA_VERSION`.

- Todas las coordenadas son píxeles de la imagen de referencia de cada página (CO-04):
  nada asume A4. Una caja es `[x0, y0, x1, y1]`; un intervalo es `[a, b]` con `a < b`.
- Una página tiene `tablas[]` (CO-05/CO-D3). Atajo plano: si la página trae `opciones`,
  `columnas_x`, `filas` (y opcionalmente `observacion_x`) al nivel de la página, se interpreta
  como una única tabla, como en el ejemplo de `plan.md`.
- `item` es único en toda la plantilla (los formularios de varias hojas numeran seguido).
"""

import json
import re
from pathlib import Path
from typing import Annotated, Literal, Self

from openpyxl.utils import range_boundaries
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

ESQUEMA_VERSION = 1

_CLAVES_TABLA_PLANA = ("opciones", "columnas_x", "observacion_x", "filas")


def _intervalo(v: list[int]) -> list[int]:
    if v[0] >= v[1]:
        raise ValueError(f"el intervalo {v} debe cumplir inicio < fin")
    return v


def _caja(v: list[int]) -> list[int]:
    if v[0] >= v[2] or v[1] >= v[3]:
        raise ValueError(f"la caja {v} debe cumplir x0 < x1 e y0 < y1")
    return v


Intervalo = Annotated[list[int], Field(min_length=2, max_length=2), AfterValidator(_intervalo)]
Caja = Annotated[list[int], Field(min_length=4, max_length=4), AfterValidator(_caja)]


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _ordenados_sin_solape(nombre: str, tramos: list[list[int]]) -> None:
    for i in range(1, len(tramos)):
        ant, act = tramos[i - 1], tramos[i]
        if act[0] < ant[1]:
            raise ValueError(
                f"{nombre}: el tramo {i + 1} {act} se solapa con el anterior {ant} "
                "o no está ordenado de menor a mayor"
            )


class CampoCabecera(_Modelo):
    campo: str = Field(min_length=1)
    caja: Caja
    tipo: Literal["texto"] = "texto"


_CELDA = re.compile(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$")


class Fila(_Modelo):
    item: int = Field(ge=1)
    texto: str = ""
    y: Intervalo
    # Celda del libro de Excel de la usuaria donde va el valor de este ítem («A19»); ver `Libro`.
    celda: str | None = None

    @model_validator(mode="after")
    def _celda_valida(self) -> Self:
        if self.celda is not None and not _CELDA.fullmatch(self.celda):
            raise ValueError(f"celda de Excel no válida: «{self.celda}» (se espera algo como A19)")
        return self


class Tabla(_Modelo):
    # «marcas»: el valor es la casilla marcada. «digito»: una sola columna con un número escrito
    # a mano; `opciones` son los dígitos permitidos y se leen con OCR de vocabulario cerrado.
    tipo: Literal["marcas", "digito"] = "marcas"
    seccion: str | None = (
        None  # agrupa tablas en secciones («5.2 Lenguaje denominativo»); solo informa
    )
    opciones: list[str] = Field(min_length=1)
    columnas_x: list[Intervalo] = Field(min_length=1)
    observacion_x: Intervalo | None = None
    filas: list[Fila] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherente(self) -> Self:
        if self.tipo == "digito":
            if len(self.columnas_x) != 1:
                raise ValueError(
                    "una tabla de dígitos tiene una sola columna (la celda del número)"
                )
            malos = [o for o in self.opciones if len(o) != 1 or not o.isdigit()]
            if malos:
                raise ValueError(f"los dígitos permitidos deben ser 0-9 de un carácter: {malos}")
        if len(self.opciones) != len(self.columnas_x) and self.tipo == "marcas":
            raise ValueError(
                f"opciones ({len(self.opciones)}) y columnas_x ({len(self.columnas_x)}) "
                "deben tener la misma longitud"
            )
        _ordenados_sin_solape("columnas_x", self.columnas_x)
        _ordenados_sin_solape("filas", [f.y for f in self.filas])
        if self.observacion_x is not None and self.observacion_x[0] < self.columnas_x[-1][1]:
            raise ValueError("observacion_x se solapa con columnas_x o queda a su izquierda")
        return self


class Pagina(_Modelo):
    imagen_referencia: str = Field(min_length=1)
    tamano_px: Annotated[list[int], Field(min_length=2, max_length=2)]
    cabecera: list[CampoCabecera] = []
    tablas: list[Tabla] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _atajo_plano(cls, datos: object) -> object:
        if not isinstance(datos, dict):
            return datos
        planas = [k for k in _CLAVES_TABLA_PLANA if k in datos]
        if not planas:
            return datos
        if "tablas" in datos:
            raise ValueError(
                "usa `tablas` o el formato plano (opciones/columnas_x/filas), no ambos"
            )
        datos = dict(datos)
        datos["tablas"] = [{k: datos.pop(k) for k in planas}]
        return datos

    @model_validator(mode="after")
    def _dentro_de_la_imagen(self) -> Self:
        ancho, alto = self.tamano_px
        if ancho <= 0 or alto <= 0:
            raise ValueError("tamano_px debe ser positivo")
        for c in self.cabecera:
            if c.caja[0] < 0 or c.caja[1] < 0 or c.caja[2] > ancho or c.caja[3] > alto:
                raise ValueError(
                    f"cabecera '{c.campo}': la caja {c.caja} sale de tamano_px {self.tamano_px}"
                )
        nombres = [c.campo for c in self.cabecera]
        repetidos = sorted({n for n in nombres if nombres.count(n) > 1})
        if repetidos:
            raise ValueError(f"cabecera: campos repetidos {repetidos}")
        for n, t in enumerate(self.tablas, start=1):
            horizontales = [*t.columnas_x, *([t.observacion_x] if t.observacion_x else [])]
            if horizontales[0][0] < 0 or horizontales[-1][1] > ancho:
                raise ValueError(
                    f"tablas[{n}]: columnas_x/observacion_x salen de la imagen (ancho {ancho})"
                )
            if t.filas[0].y[0] < 0 or t.filas[-1].y[1] > alto:
                raise ValueError(f"tablas[{n}]: filas salen de la imagen (alto {alto})")
        return self


class Libro(_Modelo):
    """Libro de Excel de la usuaria que sirve de molde de la salida (VD-R3).

    La exportación llena una **copia** de `archivo` (que vive junto al .json de la plantilla):
    vacía los rangos de `vaciar` y escribe cada ítem en su `celda`. Fórmulas y formato quedan.
    """

    archivo: str = Field(min_length=1)
    hoja: str | None = None  # por defecto, la primera
    vaciar: list[str] = []  # rangos que se limpian antes de escribir: «A1:L58», «I63:I71»…
    celda_paciente: str | None = None  # dónde se escribe el nombre que pone la usuaria («N1»)
    conservar: list[
        str
    ] = []  # celdas que no se vacían aunque caigan en un rango: rótulos fijos («J15»)

    @model_validator(mode="after")
    def _rangos(self) -> Self:
        for r in self.vaciar:
            try:
                range_boundaries(r)
            except (ValueError, TypeError) as e:
                raise ValueError(f"rango de Excel no válido en `vaciar`: «{r}»") from e
        for c in self.conservar:
            if not _CELDA.fullmatch(c):
                raise ValueError(f"celda de Excel no válida en `conservar`: «{c}»")
        if self.celda_paciente is not None and not _CELDA.fullmatch(self.celda_paciente):
            raise ValueError(
                f"celda de Excel no válida para el paciente: «{self.celda_paciente}» (se espera algo como N1)"
            )
        return self


class UmbralesOMR(_Modelo):
    """CO-02: parámetros de decisión de casilla; se ajustan por plantilla (PI-R2)."""

    tinta_minima: float = Field(default=0.03, ge=0, le=1)
    margen_relativo: float = Field(default=0.25, ge=0, le=1)


class Plantilla(_Modelo):
    esquema_version: int = ESQUEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    nombre: str = Field(min_length=1)
    version: int = Field(ge=1)
    omr: UmbralesOMR = UmbralesOMR()
    libro: Libro | None = None
    paginas: list[Pagina] = Field(min_length=1)

    @model_validator(mode="after")
    def _validar(self) -> Self:
        if self.esquema_version != ESQUEMA_VERSION:
            raise ValueError(
                f"esquema_version {self.esquema_version} no soportada (se espera {ESQUEMA_VERSION})"
            )
        items = [f.item for p in self.paginas for t in p.tablas for f in t.filas]
        repetidos = sorted({i for i in items if items.count(i) > 1})
        if repetidos:
            raise ValueError(f"item repetidos en la plantilla: {repetidos}")
        celdas = [f.celda for p in self.paginas for t in p.tablas for f in t.filas if f.celda]
        iguales = sorted({c for c in celdas if celdas.count(c) > 1})
        if iguales:
            raise ValueError(f"dos ítems escriben en la misma celda del Excel: {iguales}")
        if self.libro is not None and self.libro.celda_paciente in celdas:
            raise ValueError(
                f"la celda del paciente ({self.libro.celda_paciente}) es la de un ítem del Excel"
            )
        return self


class PlantillaInvalida(ValueError):
    """La plantilla no cumple el esquema; el mensaje nombra cada campo con error."""


def _mensaje(ruta: Path, e: ValidationError) -> str:
    lineas = []
    for err in e.errors():
        campo = ".".join(str(p) for p in err["loc"]) or "(raíz)"
        msg = str(err["msg"]).removeprefix("Value error, ")
        lineas.append(f"  - {campo}: {msg}")
    return f"Plantilla inválida {ruta}:\n" + "\n".join(lineas)


def cargar_plantilla(ruta: str | Path) -> Plantilla:
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PlantillaInvalida(f"Plantilla inválida {ruta}: JSON mal formado ({e})") from e
    try:
        return Plantilla.model_validate(datos)
    except ValidationError as e:
        raise PlantillaInvalida(_mensaje(ruta, e)) from e
