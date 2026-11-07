"""CO-R7: orquesta foto → hoja → registro → casillas → `Evaluacion`.

`procesar_foto` encadena los pasos de `core` (carga y calidad, detección de hoja, registro contra
la referencia, lectura de casillas) y devuelve un `Procesamiento`:

- `resultado`: `ResultadoProcesamiento`, **serializable** (`a_dict()` → JSON); es lo que usará la
  app (AP-R1) y lo que viaja al visor de revisión. No lleva imágenes.
- `registro`: el `Registro` con la hoja enderezada, para dibujar la depuración o recortar celdas.

Los errores de la foto (`ImagenInvalida`, `HojaNoEncontrada`) no se capturan aquí: llegan tal cual
a quien llama, con un mensaje apto para la usuaria. Un registro dudoso o una foto con mala calidad
**no** son errores: quedan en el resultado como banderas/problemas y la revisión es obligatoria.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from math import isfinite

import numpy as np

from autoevalpsi.core.casillas import ParametrosLectura, ResultadoFila, leer_casillas
from autoevalpsi.core.excel import Evaluacion, FilaEvaluacion
from autoevalpsi.core.imagen import UmbralesCalidad, cargar_imagen, evaluar_calidad
from autoevalpsi.core.plantilla import Plantilla
from autoevalpsi.core.registro import Registro, UmbralesRegistro, registrar


def _numero(x: float) -> float | None:
    """JSON no admite inf/nan."""
    return round(float(x), 4) if isfinite(x) else None


@dataclass(frozen=True)
class ResultadoProcesamiento:
    plantilla_id: str
    plantilla_version: int
    pagina: int
    foto_sha256: str
    problemas_calidad: tuple[str, ...]
    registro: dict
    filas: tuple[ResultadoFila, ...]

    @property
    def registro_ok(self) -> bool:
        return bool(self.registro["ok"])

    @property
    def n_amarillas(self) -> int:
        return sum(1 for f in self.filas if not f.ok)

    @property
    def requiere_revision(self) -> bool:
        """Hay algo que mirar: registro dudoso, mala calidad o alguna fila con bandera."""
        return (not self.registro_ok) or bool(self.problemas_calidad) or self.n_amarillas > 0

    def a_dict(self) -> dict:
        return {
            "plantilla": {"id": self.plantilla_id, "version": self.plantilla_version},
            "pagina": self.pagina,
            "foto_sha256": self.foto_sha256,
            "problemas_calidad": list(self.problemas_calidad),
            "registro": self.registro,
            "filas": [
                {
                    "item": f.item,
                    "opcion": f.opcion,
                    "proporciones": [round(p, 4) for p in f.proporciones],
                    "banderas": list(f.banderas),
                    "contraste": _numero(f.contraste),
                }
                for f in self.filas
            ],
            "requiere_revision": self.requiere_revision,
        }


@dataclass(frozen=True)
class Procesamiento:
    resultado: ResultadoProcesamiento
    registro: Registro  # con la hoja enderezada (no serializable)


def _resumen_registro(r: Registro) -> dict:
    return {
        "ok": r.ok,
        "metodo_hoja": r.metodo_hoja,
        "giro": r.giro,
        "coincidencias": r.coincidencias,
        "inliers": r.inliers,
        "proporcion_inliers": _numero(r.proporcion_inliers),
        "error_reproyeccion": _numero(r.error_reproyeccion),
        "cobertura": _numero(r.cobertura),
        "correlacion_lineas": _numero(r.correlacion_lineas),
        "ajuste_lineas": r.ajuste_lineas,
        "banderas": list(r.banderas),
    }


def procesar_foto(
    datos: bytes,
    plantilla: Plantilla,
    referencia: np.ndarray,
    *,
    pagina: int = 0,
    umbrales_calidad: UmbralesCalidad | None = None,
    umbrales_registro: UmbralesRegistro | None = None,
    parametros: ParametrosLectura | None = None,
) -> Procesamiento:
    """Foto (bytes JPEG/PNG) → lectura de las casillas de la página `pagina` (0-based).

    `referencia` es la imagen en blanco (gris) de esa página.
    Lanza `ImagenInvalida` / `HojaNoEncontrada` / `RegistroInvalido` (todas `ValueError`).
    """
    imagen = cargar_imagen(datos)
    calidad = evaluar_calidad(imagen, umbrales_calidad)
    registro = registrar(imagen, referencia, umbrales=umbrales_registro)
    leidas = leer_casillas(registro, plantilla, referencia, pagina=pagina, parametros=parametros)
    resultado = ResultadoProcesamiento(
        plantilla_id=plantilla.id,
        plantilla_version=plantilla.version,
        pagina=pagina,
        foto_sha256=hashlib.sha256(datos).hexdigest(),
        problemas_calidad=tuple(calidad.problemas),
        registro=_resumen_registro(registro),
        filas=leidas.filas,
    )
    return Procesamiento(resultado, registro)


def a_evaluacion(
    resultado: ResultadoProcesamiento,
    plantilla: Plantilla,
    *,
    paciente: str = "",
    fecha: date | None = None,
    id: str | None = None,
    cabecera: dict[str, str] | None = None,
) -> Evaluacion:
    """Convierte la lectura en la `Evaluacion` que exporta `core.excel`.

    `revisado` es verdadero solo en las filas sin bandera (verdes): las amarillas quedan sin
    revisar hasta que la persona las confirme. Sin `id`, se deriva de la foto (SHA-256): procesar
    dos veces la misma foto no duplica la fila del consolidado.
    """
    filas = tuple(FilaEvaluacion(f.item, f.opcion, revisado=f.ok) for f in resultado.filas)
    return Evaluacion(
        id=id or resultado.foto_sha256[:12],
        plantilla=plantilla,
        fecha=fecha or date.today(),
        paciente=paciente,
        filas=filas,
        cabecera=cabecera or {},
    )
