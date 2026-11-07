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
from dataclasses import dataclass, field
from datetime import date
from math import isfinite

import numpy as np

from autoevalpsi.core.casillas import ParametrosLectura, ResultadoFila, leer_casillas
from autoevalpsi.core.excel import Evaluacion, FilaEvaluacion
from autoevalpsi.core.imagen import UmbralesCalidad, cargar_imagen, evaluar_calidad
from autoevalpsi.core.ocr.lector import Lector
from autoevalpsi.core.ocr.texto import CampoLeido, ObservacionLeida, ParametrosOCR, leer_texto
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
    ocr_activo: bool = False  # False: no se leyó texto (sin lector); no es lo mismo que «vacío»
    observaciones: tuple[ObservacionLeida, ...] = ()
    cabecera: tuple[CampoLeido, ...] = ()

    @property
    def registro_ok(self) -> bool:
        return bool(self.registro["ok"])

    @property
    def items_amarillos(self) -> frozenset[int]:
        """Ítems con bandera en las casillas o en la observación."""
        return frozenset(
            [f.item for f in self.filas if not f.ok]
            + [o.item for o in self.observaciones if not o.ok]
        )

    @property
    def n_amarillas(self) -> int:
        return len(self.items_amarillos)

    @property
    def n_cabecera_dudosa(self) -> int:
        return sum(1 for c in self.cabecera if not c.ok)

    @property
    def requiere_revision(self) -> bool:
        """Hay algo que mirar: registro dudoso, mala calidad, una fila o la cabecera con bandera."""
        return (
            (not self.registro_ok)
            or bool(self.problemas_calidad)
            or self.n_amarillas > 0
            or self.n_cabecera_dudosa > 0
        )

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
            "ocr_activo": self.ocr_activo,
            "observaciones": [
                {
                    "item": o.item,
                    "texto": o.texto,
                    "confianza": None if o.confianza is None else _numero(o.confianza),
                    "tiene_tinta": o.tiene_tinta,
                    "banderas": list(o.banderas),
                }
                for o in self.observaciones
            ],
            "cabecera": [
                {
                    "campo": c.campo,
                    "texto": c.texto,
                    "confianza": None if c.confianza is None else _numero(c.confianza),
                    "tiene_tinta": c.tiene_tinta,
                    "banderas": list(c.banderas),
                }
                for c in self.cabecera
            ],
            "requiere_revision": self.requiere_revision,
        }


@dataclass(frozen=True)
class Procesamiento:
    resultado: ResultadoProcesamiento
    registro: Registro  # con la hoja enderezada (no serializable)
    recortes: dict[int, np.ndarray] = field(default_factory=dict)  # item -> recorte de observación
    recortes_cabecera: dict[str, np.ndarray] = field(default_factory=dict)


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
    lector: Lector | None = None,
    parametros_ocr: ParametrosOCR | None = None,
) -> Procesamiento:
    """Foto (bytes JPEG/PNG) → lectura de las casillas de la página `pagina` (0-based).

    `referencia` es la imagen en blanco (gris) de esa página. Con `lector`, además se leen las
    observaciones y la cabecera (OC-R2); sin él solo las casillas. Un fallo del lector no lanza:
    queda como bandera `ocr_error` y los recortes se conservan.
    Lanza `ImagenInvalida` / `HojaNoEncontrada` / `RegistroInvalido` (todas `ValueError`).
    """
    imagen = cargar_imagen(datos)
    calidad = evaluar_calidad(imagen, umbrales_calidad)
    registro = registrar(imagen, referencia, umbrales=umbrales_registro)
    leidas = leer_casillas(registro, plantilla, referencia, pagina=pagina, parametros=parametros)
    texto = (
        leer_texto(
            registro.imagen, plantilla, referencia, lector, pagina=pagina, parametros=parametros_ocr
        )
        if lector is not None
        else None
    )
    resultado = ResultadoProcesamiento(
        plantilla_id=plantilla.id,
        plantilla_version=plantilla.version,
        pagina=pagina,
        foto_sha256=hashlib.sha256(datos).hexdigest(),
        problemas_calidad=tuple(calidad.problemas),
        registro=_resumen_registro(registro),
        filas=leidas.filas,
        ocr_activo=texto is not None,
        observaciones=texto.observaciones if texto else (),
        cabecera=texto.cabecera if texto else (),
    )
    return Procesamiento(
        resultado,
        registro,
        texto.recortes if texto else {},
        texto.recortes_cabecera if texto else {},
    )


def nombre_campo_cabecera(campo: str) -> str:
    """Nombre con que un campo de cabecera leído figura en `Evaluacion.cabecera` (y en el Excel)."""
    return "Fecha manuscrita" if campo == "fecha" else campo.capitalize()


def a_evaluacion(
    resultado: ResultadoProcesamiento,
    plantilla: Plantilla,
    *,
    paciente: str = "",
    fecha: date | None = None,
    id: str | None = None,
    cabecera: dict[str, str] | None = None,
    recortes: dict[int, np.ndarray] | None = None,
) -> Evaluacion:
    """Convierte la lectura en la `Evaluacion` que exporta `core.excel`.

    `revisado` es verdadero solo en las filas sin bandera (verdes), ni en las casillas ni en la
    observación: las amarillas quedan sin revisar hasta que la persona las confirme. Sin `id`, se
    deriva de la foto (SHA-256): procesar dos veces la misma foto no duplica la fila del
    consolidado.

    Con OCR, el texto leído de la cabecera completa lo que no se pasó a mano: `paciente` si va
    vacío, y los demás campos en `cabecera` (la fecha manuscrita, como texto, en «Fecha manuscrita»;
    la `fecha` de la evaluación sigue siendo el argumento o hoy). Lo pasado a mano manda.
    """
    obs = {o.item: o for o in resultado.observaciones}
    filas = tuple(
        FilaEvaluacion(
            f.item,
            f.opcion,
            observacion=obs[f.item].texto if f.item in obs else "",
            revisado=f.item not in resultado.items_amarillos,
            recorte=(recortes or {}).get(f.item),
        )
        for f in resultado.filas
    )
    leida = {c.campo: c.texto for c in resultado.cabecera if c.texto}
    extra = {nombre_campo_cabecera(k): v for k, v in leida.items() if k != "paciente"}
    return Evaluacion(
        id=id or resultado.foto_sha256[:12],
        plantilla=plantilla,
        fecha=fecha or date.today(),
        paciente=paciente or leida.get("paciente", ""),
        filas=filas,
        cabecera={**extra, **(cabecera or {})},
    )
