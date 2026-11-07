"""OC-R2: lectura de las observaciones por fila y de la cabecera sobre la hoja registrada.

Entrada: la hoja ya registrada (`Registro.imagen`, en coordenadas de la plantilla) y un `Lector`.

**Observaciones (OC-05).** Por cada tabla con `observacion_x`:

1. La zona de observaciones (todas las filas, una sola franja) se limpia: lo impreso de la
   referencia (líneas, texto) se pinta de blanco, y también las filas **sin tinta**, de modo que el
   detector no alucine texto donde no hay nada.
2. El lector corre **una sola vez** sobre la franja (nunca una vez por fila). Si ninguna fila tiene
   tinta, no se llama al lector.
3. Cada línea leída se asigna a la fila en cuya franja vertical cae su centro; varias líneas de la
   misma fila se unen en orden de lectura, con la confianza de la peor.

**Recorte siempre (OC-02).** De cada fila con tinta se conserva el recorte original (sin limpiar)
de su celda de observación, haya leído bien, mal o nada el lector: es la red de seguridad de la
revisión. Las filas sin tinta no llevan recorte.

**Cabecera (CO-03).** Cada campo de `Pagina.cabecera` se lee por separado sobre su caja.

**Banderas** (la fila/campo queda «amarillo»; la revisión es obligatoria):

- `ocr_confianza_baja`: la confianza del lector bajo el umbral;
- `ocr_sin_texto`: hay tinta pero el lector no encontró texto;
- `ocr_error`: el lector falló (excepción); el recorte se conserva;
- `cabecera_vacia`: un campo de cabecera sin tinta (solo cabecera: una observación vacía es normal).

Principio: el texto leído es una sugerencia; nunca se da por bueno sin bandera si hay duda.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from autoevalpsi.core.casillas import ParametrosLectura, mascara_impreso, medir_celda
from autoevalpsi.core.ocr.lector import Lector, Linea
from autoevalpsi.core.plantilla import Plantilla, Tabla

BANDERA_OCR_CONFIANZA_BAJA = "ocr_confianza_baja"
BANDERA_OCR_SIN_TEXTO = "ocr_sin_texto"
BANDERA_OCR_ERROR = "ocr_error"
BANDERA_CABECERA_VACIA = "cabecera_vacia"


@dataclass(frozen=True)
class ParametrosOCR:
    """Umbrales de la lectura de texto; se calibran con letra real en OC-R3."""

    tinta_minima: float = 0.004  # fracción de la celda con tinta para considerarla escrita
    confianza_minima: float = 0.85  # bajo esto: `ocr_confianza_baja`
    holgura_impreso_px: int = 4  # engrosado de lo impreso al limpiar (error residual del registro)
    medicion: ParametrosLectura = field(default_factory=ParametrosLectura)


@dataclass(frozen=True)
class ObservacionLeida:
    item: int
    texto: str
    confianza: float | None  # None: no se leyó nada
    tiene_tinta: bool
    banderas: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.banderas


@dataclass(frozen=True)
class CampoLeido:
    campo: str
    texto: str
    confianza: float | None
    tiene_tinta: bool
    banderas: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.banderas


@dataclass(frozen=True)
class ResultadoTexto:
    observaciones: tuple[ObservacionLeida, ...]
    cabecera: tuple[CampoLeido, ...]
    recortes: dict[int, np.ndarray]  # item -> recorte original de su observación (con tinta)
    recortes_cabecera: dict[str, np.ndarray]  # campo -> recorte original (con tinta)


def _gris(imagen: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen


def _unir(lineas: list[Linea]) -> tuple[str, float | None]:
    """Texto en orden de lectura y confianza de la peor línea."""
    if not lineas:
        return "", None
    texto = " ".join(li.texto.strip() for li in lineas if li.texto.strip())
    return texto, min(li.confianza for li in lineas)


def _banderas(
    tiene_tinta: bool, lineas: list[Linea], confianza: float | None, error: bool, p: ParametrosOCR
) -> tuple[str, ...]:
    if not tiene_tinta:
        return ()
    if error:
        return (BANDERA_OCR_ERROR,)
    if not lineas or confianza is None:
        return (BANDERA_OCR_SIN_TEXTO,)
    if confianza < p.confianza_minima:
        return (BANDERA_OCR_CONFIANZA_BAJA,)
    return ()


def _leer_o_fallar(lector: Lector, imagen: np.ndarray) -> tuple[list[Linea], bool]:
    """(líneas, hubo_error). Un fallo del lector nunca tumba el pipeline: se anota en banderas.

    Salvo la instalación: modelos ausentes (`FileNotFoundError`) o `onnxruntime` sin instalar
    (`ImportError`) no son un problema de la foto y se propagan con su mensaje de remedio."""
    try:
        return list(lector.leer(imagen)), False
    except (FileNotFoundError, ImportError):
        raise
    except Exception:  # noqa: BLE001 - cualquier fallo del modelo: se degrada a `ocr_error`
        return [], True


def _fila_de(centro_y: float, tramos: list[tuple[int, int]]) -> int | None:
    """Índice de la fila cuyo tramo contiene `centro_y`; si cae en un hueco, la más cercana a
    menos de media fila; si no, ninguna."""
    for k, (a, b) in enumerate(tramos):
        if a <= centro_y < b:
            return k
    k = min(range(len(tramos)), key=lambda i: min(abs(centro_y - tramos[i][0]),
                                                  abs(centro_y - tramos[i][1])))  # fmt: skip
    a, b = tramos[k]
    return k if min(abs(centro_y - a), abs(centro_y - b)) <= (b - a) / 2 else None


def _leer_tabla(
    img: np.ndarray,
    gris: np.ndarray,
    limpia: np.ndarray,
    impreso: np.ndarray,
    tabla: Tabla,
    lector: Lector,
    p: ParametrosOCR,
) -> tuple[list[ObservacionLeida], dict[int, np.ndarray]]:
    assert tabla.observacion_x is not None
    x0, x1 = tabla.observacion_x
    tinta: list[bool] = []
    for fila in tabla.filas:
        caja = (x0, fila.y[0], x1, fila.y[1])
        mx, my = (x1 - x0) // 2, (fila.y[1] - fila.y[0]) // 2
        ventana = (x0 - mx, fila.y[0] - my, x1 + mx, fila.y[1] + my)
        prop, _ = medir_celda(gris, caja, ventana, impreso, p.medicion)
        tinta.append(prop >= p.tinta_minima)

    recortes = {
        f.item: img[f.y[0] : f.y[1], x0:x1].copy()
        for f, con in zip(tabla.filas, tinta, strict=True)
        if con
    }

    asignadas: list[list[Linea]] = [[] for _ in tabla.filas]
    error = False
    if any(tinta):
        franja_y0, franja_y1 = tabla.filas[0].y[0], tabla.filas[-1].y[1]
        franja = limpia[franja_y0:franja_y1, x0:x1].copy()
        for f, con in zip(tabla.filas, tinta, strict=True):
            if not con:  # sin tinta: se blanquea para que el detector no invente texto
                franja[f.y[0] - franja_y0 : f.y[1] - franja_y0] = 255
        lineas, error = _leer_o_fallar(lector, franja)
        tramos = [(f.y[0], f.y[1]) for f in tabla.filas]
        for li in lineas:
            k = _fila_de(li.caja.centro_y + franja_y0, tramos)
            if k is not None and tinta[k]:
                asignadas[k].append(li)

    salida = []
    for fila, con, lineas in zip(tabla.filas, tinta, asignadas, strict=True):
        texto, conf = _unir(lineas)
        salida.append(
            ObservacionLeida(fila.item, texto, conf, con, _banderas(con, lineas, conf, error, p))
        )
    return salida, recortes


def leer_texto(
    imagen: np.ndarray,
    plantilla: Plantilla,
    referencia: np.ndarray,
    lector: Lector,
    *,
    pagina: int = 0,
    parametros: ParametrosOCR | None = None,
) -> ResultadoTexto:
    """Lee observaciones y cabecera de la página `pagina` (0-based) de la hoja registrada.

    `imagen` es `Registro.imagen`; `referencia` la hoja en blanco de esa página.
    """
    p = parametros or ParametrosOCR()
    datos = plantilla.paginas[pagina]
    ancho, alto = datos.tamano_px
    if imagen.shape[:2] != (alto, ancho) or referencia.shape[:2] != (alto, ancho):
        raise ValueError(
            f"imagen {imagen.shape[1]}x{imagen.shape[0]} y referencia "
            f"{referencia.shape[1]}x{referencia.shape[0]} no coinciden con la página de la "
            f"plantilla {ancho}x{alto}"
        )
    gris = _gris(imagen)
    suave = cv2.GaussianBlur(gris, (0, 0), p.medicion.desenfoque_sigma) if (
        p.medicion.desenfoque_sigma > 0
    ) else gris  # fmt: skip
    impreso = mascara_impreso(referencia, p.holgura_impreso_px)
    limpia = gris.copy()
    limpia[impreso] = 255

    observaciones: list[ObservacionLeida] = []
    recortes: dict[int, np.ndarray] = {}
    for tabla in datos.tablas:
        if tabla.observacion_x is None:
            continue
        obs, rec = _leer_tabla(imagen, suave, limpia, impreso, tabla, lector, p)
        observaciones += obs
        recortes.update(rec)

    cabecera: list[CampoLeido] = []
    recortes_cabecera: dict[str, np.ndarray] = {}
    for campo in datos.cabecera:
        x0, y0, x1, y1 = campo.caja
        mx, my = (x1 - x0) // 2, (y1 - y0) // 2
        prop, _ = medir_celda(suave, (x0, y0, x1, y1), (x0 - mx, y0 - my, x1 + mx, y1 + my),
                              impreso, p.medicion)  # fmt: skip
        con = prop >= p.tinta_minima
        if not con:
            cabecera.append(CampoLeido(campo.campo, "", None, False, (BANDERA_CABECERA_VACIA,)))
            continue
        recortes_cabecera[campo.campo] = imagen[y0:y1, x0:x1].copy()
        lineas, error = _leer_o_fallar(lector, limpia[y0:y1, x0:x1])
        texto, conf = _unir(lineas)
        cabecera.append(
            CampoLeido(campo.campo, texto, conf, True, _banderas(True, lineas, conf, error, p))
        )
    return ResultadoTexto(tuple(observaciones), tuple(cabecera), recortes, recortes_cabecera)
