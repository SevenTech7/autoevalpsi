"""CO-R5: lectura de casillas (OMR) sobre la hoja registrada.

`leer_casillas(registro, plantilla)` recorre cada fila de cada tabla de la página y decide qué
opción está marcada, sobre `Registro.imagen` (CO-R3), que ya está en las coordenadas de la
plantilla. Por celda:

1. **Celda completa menos lo impreso**: las líneas de la cuadrícula (y cualquier texto impreso)
   salen de la imagen en blanco de la plantilla (`referencia`), engrosadas `holgura_impreso`
   para absorber el error residual del registro. No se recorta con margen interior: un círculo o
   una X grandes dejan su trazo sobre el borde de la celda y un margen los atribuiría a la vecina
   (error silencioso, visto con otra semilla del lote sintético).
2. **Umbral adaptativo**: el fondo de cada celda es un percentil alto del gris de una ventana
   más ancha que la celda (robusto a sombras y a una marca que la llene entera); un píxel es
   tinta si está `delta_tinta` niveles por debajo.
3. **Proporción de tinta** = píxeles de tinta / área del recorte.

Decisión por fila (CO-02), con los umbrales de la plantilla (`Plantilla.omr`):

- la mayor proporción `p1` < `tinta_minima` → `sin_marca`, `opcion=None`;
- la segunda `p2` ≥ `tinta_minima` y dentro del margen relativo de `p1`
  (`p2 > (1 - margen_relativo) * p1`) → `doble_marca`, `opcion=None` (no se adivina: tachón,
  doble respuesta);
- `p2` ≥ `tinta_minima` pero `p1` domina → gana `p1` **con** `doble_marca` (hay otra marca; que
  la persona confirme);
- la ganadora con poca profundidad de tinta (marca tenue) → `contraste_bajo`.

Si el registro es dudoso (CO-09), **todas** las filas llevan `registro_dudoso` (revisión
obligatoria de la página). Principio: ninguna fila sale con una opción equivocada sin bandera.
Una fila con bandera es «amarilla»; sin bandera es «verde».
"""

from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from autoevalpsi.core.ocr.lector import LectorDigitos
from autoevalpsi.core.plantilla import Plantilla, Tabla
from autoevalpsi.core.registro import BANDERA_REGISTRO_DUDOSO, Registro

BANDERA_SIN_MARCA = "sin_marca"
BANDERA_DOBLE_MARCA = "doble_marca"
BANDERA_CONTRASTE_BAJO = "contraste_bajo"
# Tablas de dígitos manuscritos (el valor es un número, no una casilla marcada):
BANDERA_CELDA_VACIA = "celda_vacia"  # no hay nada escrito: queda vacía, pero se avisa
BANDERA_DIGITO_DUDOSO = "ocr_digito_dudoso"  # hay un número, pero la lectura no es nítida
BANDERA_DIGITO_ILEGIBLE = "ocr_digito_ilegible"  # hay tinta y no se pudo leer ningún dígito
BANDERA_SIN_LECTOR = "ocr_sin_lector"  # no hay lector de texto: se escribe a mano


@dataclass(frozen=True)
class ParametrosLectura:
    """Parámetros de medición de tinta (no son contrato de plantilla; ver `Plantilla.omr`)."""

    holgura_impreso: float = 0.03  # engrosado de lo impreso, fracción del lado menor de la celda
    delta_tinta: int = 40  # niveles de gris bajo el fondo para contar un píxel como tinta
    percentil_fondo: float = 85.0
    contraste_min: float = 100.0  # profundidad mínima de la tinta de la ganadora (0-255)
    desenfoque_sigma: float = 1.0  # quita el ruido de grano/JPEG antes de umbralizar
    delta_digito_min: float = 22.0  # caída mínima de gris (0-255) para contar un píxel como tinta
    delta_digito_rel: float = 0.28  # …o esta fracción del gris del papel, si es mayor
    tinta_digito: float = 0.008  # tinta mínima de una celda de dígito para considerarla escrita
    digito_confianza: float = 0.6  # por debajo: el dígito se propone pero se marca como dudoso
    digito_margen: float = 0.3  # distancia mínima al segundo dígito para no marcarlo dudoso
    digito_ilegible: float = 0.3  # por debajo de esta confianza no se propone ningún dígito
    margen_celda: float = 0.18  # fracción de la celda que se descarta (líneas de la cuadrícula)


@dataclass(frozen=True)
class ResultadoFila:
    item: int
    opcion: str | None
    proporciones: tuple[float, ...]  # una por opción, 0-1
    banderas: tuple[str, ...] = field(default_factory=tuple)
    contraste: float = 0.0  # profundidad de la tinta en la celda con más tinta (0-255)

    @property
    def ok(self) -> bool:
        """Verde: la opción se leyó sin ninguna bandera."""
        return not self.banderas


@dataclass(frozen=True)
class ResultadoPagina:
    filas: tuple[ResultadoFila, ...]
    registro_ok: bool
    # la celda de cada número manuscrito, para que la usuaria lo compare en la revisión
    recortes: dict[int, np.ndarray] = field(default_factory=dict)

    @property
    def banderas(self) -> tuple[str, ...]:
        return () if self.registro_ok else (BANDERA_REGISTRO_DUDOSO,)

    def por_item(self) -> dict[int, ResultadoFila]:
        return {f.item: f for f in self.filas}


def _gris(imagen: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen


def mascara_impreso(referencia: np.ndarray, radio: int) -> np.ndarray:
    """True donde la referencia tiene tinta de imprenta (líneas, texto), engrosado `radio` px."""
    oscuro = (_gris(referencia) < 128).astype(np.uint8)
    if radio > 0:
        nucleo = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * radio + 1, 2 * radio + 1))
        oscuro = cv2.dilate(oscuro, nucleo)
    return oscuro.astype(bool)


def medir_celda(
    gris: np.ndarray,
    caja: tuple[int, int, int, int],
    ventana: tuple[int, int, int, int],
    impreso: np.ndarray,
    p: ParametrosLectura,
):
    """(proporción de tinta, profundidad de la tinta) de una celda, sin contar lo impreso.

    `ventana` (x0, y0, x1, y1) es la zona de la que sale el fondo: la celda con la mitad de su
    tamaño de más por cada lado, para que una marca que llene la celda no se confunda con papel.
    """
    x0, y0, x1, y1 = caja
    recorte = gris[y0:y1, x0:x1]
    if recorte.size == 0:
        return 0.0, 0.0
    vx0, vy0, vx1, vy1 = ventana
    alto, ancho = gris.shape[:2]
    zona = gris[max(vy0, 0) : min(vy1, alto), max(vx0, 0) : min(vx1, ancho)]
    fondo = float(np.percentile(zona, p.percentil_fondo))
    caida = fondo - recorte.astype(np.float32)
    libre = ~impreso[y0:y1, x0:x1]
    proporcion = float(((caida > p.delta_tinta) & libre).mean())
    if not libre.any():
        return proporcion, 0.0
    return proporcion, max(float(np.percentile(caida[libre], 99.0)), 0.0)


def decidir_fila(
    opciones: list[str],
    proporciones: list[float],
    profundidades: list[float],
    tinta_minima: float,
    margen_relativo: float,
    contraste_min: float,
) -> tuple[str | None, tuple[str, ...], float]:
    orden = sorted(range(len(proporciones)), key=lambda k: proporciones[k], reverse=True)
    k1 = orden[0]
    p1 = proporciones[k1]
    p2 = proporciones[orden[1]] if len(orden) > 1 else 0.0
    contraste = profundidades[k1]
    if p1 < tinta_minima:
        return None, (BANDERA_SIN_MARCA,), contraste
    banderas: list[str] = []
    opcion: str | None = opciones[k1]
    if p2 >= tinta_minima:
        banderas.append(BANDERA_DOBLE_MARCA)
        if p2 > (1.0 - margen_relativo) * p1:
            opcion = None
    if opcion is not None and contraste < contraste_min:
        banderas.append(BANDERA_CONTRASTE_BAJO)
    return opcion, tuple(banderas), contraste


def _leer_tabla(
    gris: np.ndarray,
    referencia: np.ndarray,
    tabla: Tabla,
    plantilla: Plantilla,
    p: ParametrosLectura,
) -> list[ResultadoFila]:
    ancho_celda = min(c[1] - c[0] for c in tabla.columnas_x)
    alto_celda = min(f.y[1] - f.y[0] for f in tabla.filas)
    radio = max(1, round(p.holgura_impreso * min(ancho_celda, alto_celda)))
    impreso = mascara_impreso(referencia, radio)
    filas = []
    for fila in tabla.filas:
        props, profs = [], []
        for columna in tabla.columnas_x:
            caja = (columna[0], fila.y[0], columna[1], fila.y[1])
            mx, my = (columna[1] - columna[0]) // 2, (fila.y[1] - fila.y[0]) // 2
            ventana = (columna[0] - mx, fila.y[0] - my, columna[1] + mx, fila.y[1] + my)
            prop, prof = medir_celda(gris, caja, ventana, impreso, p)
            props.append(prop)
            profs.append(prof)
        opcion, banderas, contraste = decidir_fila(
            tabla.opciones,
            props,
            profs,
            plantilla.omr.tinta_minima,
            plantilla.omr.margen_relativo,
            p.contraste_min,
        )
        filas.append(ResultadoFila(fila.item, opcion, tuple(props), banderas, contraste))
    return filas


def _leer_digitos(
    imagen: np.ndarray,
    gris: np.ndarray,
    tabla: Tabla,
    lector: LectorDigitos | None,
    p: ParametrosLectura,
) -> tuple[list[ResultadoFila], dict[int, np.ndarray]]:
    """Una fila por ítem: el dígito manuscrito de su celda, o vacía, o dudosa (nunca se adivina).

    Solo se mira el **interior** de la celda (sin el borde, donde está la cuadrícula impresa): ahí no
    hay nada impreso, así que toda tinta es lo escrito a mano. No depende de la referencia, que en
    fotos con poca luz o sombra no sirve para separar lo impreso."""
    x0, x1 = tabla.columnas_x[0]
    sin_impreso = np.zeros(gris.shape[:2], bool)
    filas = []
    recortes: dict[int, np.ndarray] = {}
    for fila in tabla.filas:
        y0, y1 = fila.y
        dx, dy = round((x1 - x0) * p.margen_celda), round((y1 - y0) * p.margen_celda)
        interior = (x0 + dx, y0 + dy, x1 - dx, y1 - dy)
        mx, my = (x1 - x0) // 2, (y1 - y0) // 2
        ventana = (x0 - mx, y0 - my, x1 + mx, y1 + my)
        # el contraste mínimo de la tinta se mide contra el papel: con poca luz el lápiz apenas
        # baja 30 niveles, con buena luz baja 100
        zona = gris[max(ventana[1], 0) : ventana[3], max(ventana[0], 0) : ventana[2]]
        fondo = float(np.percentile(zona, p.percentil_fondo))
        delta = max(p.delta_digito_min, p.delta_digito_rel * fondo)
        prop, _ = medir_celda(gris, interior, ventana, sin_impreso, replace(p, delta_tinta=delta))
        if prop < p.tinta_digito:
            filas.append(ResultadoFila(fila.item, None, (prop,), (BANDERA_CELDA_VACIA,)))
            continue
        recortes[fila.item] = imagen[y0:y1, x0:x1].copy()
        if lector is None:
            filas.append(ResultadoFila(fila.item, None, (prop,), (BANDERA_SIN_LECTOR,)))
            continue
        lectura = lector.leer_digito(
            gris[interior[1] : interior[3], interior[0] : interior[2]], tabla.opciones
        )
        if lectura.digito is None or lectura.confianza < p.digito_ilegible:
            filas.append(ResultadoFila(fila.item, None, (prop,), (BANDERA_DIGITO_ILEGIBLE,)))
        elif lectura.confianza < p.digito_confianza or lectura.margen < p.digito_margen:
            filas.append(
                ResultadoFila(fila.item, lectura.digito, (prop,), (BANDERA_DIGITO_DUDOSO,))
            )
        else:
            filas.append(ResultadoFila(fila.item, lectura.digito, (prop,)))
    return filas, recortes


def leer_casillas(
    registro: Registro,
    plantilla: Plantilla,
    referencia: np.ndarray,
    *,
    pagina: int = 0,
    parametros: ParametrosLectura | None = None,
    lector: object | None = None,
) -> ResultadoPagina:
    """Lee todas las filas de la página `pagina` (0-based) sobre la hoja registrada.

    `referencia` es la imagen en blanco de esa página (la misma que se usó en `registrar`).
    """
    p = parametros or ParametrosLectura()
    datos = plantilla.paginas[pagina]
    ancho, alto = datos.tamano_px
    if registro.imagen.shape[:2] != (alto, ancho):
        raise ValueError(
            f"la imagen registrada es {registro.imagen.shape[1]}x{registro.imagen.shape[0]} y la "
            f"página de la plantilla {ancho}x{alto}: se registró contra otra referencia"
        )
    if referencia.shape[:2] != (alto, ancho):
        raise ValueError(
            f"la referencia es {referencia.shape[1]}x{referencia.shape[0]} y la página de la "
            f"plantilla {ancho}x{alto}"
        )
    gris = _gris(registro.imagen)
    if p.desenfoque_sigma > 0:
        gris = cv2.GaussianBlur(gris, (0, 0), p.desenfoque_sigma)
    lector_digitos = lector if isinstance(lector, LectorDigitos) else None
    filas: list[ResultadoFila] = []
    recortes: dict[int, np.ndarray] = {}
    for t in datos.tablas:
        if t.tipo == "digito":
            leidas, cortes = _leer_digitos(registro.imagen, gris, t, lector_digitos, p)
            recortes.update(cortes)
        else:
            leidas = _leer_tabla(gris, referencia, t, plantilla, p)
        filas += leidas
    if not registro.ok:
        filas = [
            ResultadoFila(
                f.item,
                f.opcion,
                f.proporciones,
                (*f.banderas, BANDERA_REGISTRO_DUDOSO),
                f.contraste,
            )
            for f in filas
        ]
    return ResultadoPagina(tuple(filas), registro.ok, recortes)
