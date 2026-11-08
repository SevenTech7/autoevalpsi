"""VD-R2: detecta la cuadrícula de una hoja de respuestas con celdas numeradas (tipo Vineland).

Cada ítem es una fila de dos celdas: la **etiqueta** (número impreso: 1, 2, 3…) y, a su derecha, la
celda de **respuesta** (un número escrito a mano). Se buscan las celdas como los huecos cerrados
que dejan las líneas de la tabla; se agrupan en columnas; las columnas cuyo contenido impreso
cuenta 1, 2, 3… son de etiquetas y su vecina de la derecha es la de respuestas.

Es un **borrador**: la usuaria lo corrige en el editor de plantillas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

import cv2
import numpy as np
from openpyxl.utils import get_column_letter


@dataclass(frozen=True)
class Celda:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def ancho(self) -> int:
        return self.x1 - self.x0

    @property
    def alto(self) -> int:
        return self.y1 - self.y0


@dataclass
class Columna:
    celdas: list[Celda] = field(default_factory=list)  # de arriba abajo

    @property
    def cx(self) -> float:
        return float(np.median([c.cx for c in self.celdas]))


def _binaria(gris: np.ndarray) -> np.ndarray:
    """Líneas y tinta en blanco sobre negro; robusta a la luz amarilla y a las sombras."""
    lado = max(31, (min(gris.shape[:2]) // 25) | 1)
    suave = cv2.GaussianBlur(gris, (0, 0), 1.2)
    b = cv2.adaptiveThreshold(
        suave, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, lado, 10
    )
    return cv2.morphologyEx(b, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def huecos(gris: np.ndarray) -> list[Celda]:
    """Los recintos cerrados por líneas oscuras que pueden ser una celda, con su caja.

    Se descartan los huecos diminutos (el ojo de un 0 o de un 6 escritos a mano): una celda mide
    al menos ~2 % del ancho de la foto y ~1 % de su alto."""
    alto_foto, ancho_foto = gris.shape[:2]
    min_w, min_h = 0.02 * ancho_foto, 0.01 * alto_foto
    contornos, jerarquia = cv2.findContours(_binaria(gris), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if jerarquia is None:
        return []
    salida = []
    for c, h in zip(contornos, jerarquia[0], strict=True):
        if h[3] != -1:  # solo los huecos (contornos de segundo nivel)
            x, y, w, alto = cv2.boundingRect(c)
            if w >= min_w and alto >= min_h:
                salida.append(Celda(x, y, x + w, y + alto))
    return salida


def _mediana_tipica(huecos_: list[Celda]) -> tuple[float, float]:
    """Ancho y alto típicos de una celda: el grupo más numeroso de huecos casi cuadrados."""
    candidatos = [h for h in huecos_ if 0.6 <= h.ancho / max(h.alto, 1) <= 1.8]
    if not candidatos:
        return 0.0, 0.0
    areas = np.array([h.ancho * h.alto for h in candidatos], dtype=float)
    # el área más repetida: histograma logarítmico
    bins = np.linspace(np.log(areas.min()), np.log(areas.max()) + 1e-6, 40)
    cuenta, bordes = np.histogram(np.log(areas), bins=bins)
    k = int(cuenta.argmax())
    lo, hi = np.exp(bordes[k]) * 0.7, np.exp(bordes[k + 1]) * 1.4
    grupo = [h for h in candidatos if lo <= h.ancho * h.alto <= hi]
    return float(np.median([h.ancho for h in grupo])), float(np.median([h.alto for h in grupo]))


def celdas(gris: np.ndarray) -> tuple[list[Celda], float, float, list[Celda]]:
    """(celdas, ancho típico, alto típico, huecos grandes). Las grandes son los encabezados."""
    todos = huecos(gris)
    w, h = _mediana_tipica(todos)
    if w == 0:
        return [], 0.0, 0.0, []
    chicas = [c for c in todos if 0.6 * w <= c.ancho <= 1.5 * w and 0.6 * h <= c.alto <= 1.5 * h]
    grandes = [c for c in todos if c.ancho >= 2.2 * w and c.alto >= 1.2 * h]
    return chicas, w, h, grandes


def agrupar_columnas(cs: list[Celda], ancho: float, alto: float) -> list[Columna]:
    """Columnas de celdas, de izquierda a derecha, cada una de arriba abajo.

    Se arman de arriba abajo encadenando cada celda a la columna cuya última celda está justo
    encima y a poca distancia horizontal: así siguen una columna inclinada (la hoja de una foto
    nunca está perfectamente derecha) en vez de cortarla por su posición x."""
    columnas: list[Columna] = []
    for c in sorted(cs, key=lambda c: (c.cy, c.cx)):
        encimada = False
        mejor: Columna | None = None
        mejor_dx = 0.55 * ancho
        for col in columnas:
            ultima = col.celdas[-1]
            dy, dx = c.cy - ultima.cy, abs(c.cx - ultima.cx)
            if dy <= 0.5 * alto and dx < 0.4 * ancho:
                encimada = True  # el hueco de un hueco (una marca o un cuadro azul): se ignora
                break
            if 0.5 * alto < dy < 2.6 * alto and dx < mejor_dx:
                mejor, mejor_dx = col, dx
        if encimada:
            continue
        if mejor is not None:
            mejor.celdas.append(c)
        else:
            columnas.append(Columna([c]))
    columnas = [col for col in columnas if len(col.celdas) >= 3]
    columnas.sort(key=lambda col: col.celdas[0].cx)
    return columnas


def completar_huecos(col: Columna, alto: float) -> Columna:
    """Pone las celdas que faltan en medio de una columna (las rellenas de azul no dan hueco)."""
    celdas_ = col.celdas
    if len(celdas_) < 2:
        return col
    paso = float(np.median(np.diff([c.cy for c in celdas_])))
    x0 = int(np.median([c.x0 for c in celdas_]))
    x1 = int(np.median([c.x1 for c in celdas_]))
    salida: list[Celda] = [celdas_[0]]
    for c in celdas_[1:]:
        anterior = salida[-1]
        salto = round((c.cy - anterior.cy) / paso)
        for k in range(1, salto):
            cy = anterior.cy + (c.cy - anterior.cy) * k / salto
            salida.append(Celda(x0, int(cy - alto / 2), x1, int(cy + alto / 2)))
        salida.append(c)
    return Columna(salida)


# --- de columnas a bloques de ítems -----------------------------------------------------------


@dataclass
class BloqueItems:
    """Una columna de respuestas con sus ítems: el número impreso de cada fila y su celda."""

    seccion: str
    numeros: list[int]
    filas: list[Celda]  # la celda de respuesta de cada ítem, de arriba abajo


def _numeros_de(col: Columna, gris: np.ndarray, lector) -> list[tuple[int | None, float]]:
    out = []
    for c in col.celdas:
        mx, my = round(c.ancho * 0.14), round(c.alto * 0.14)
        out.append(lector.leer_numero(gris[c.y0 + my : c.y1 - my, c.x0 + mx : c.x1 - mx]))
    return out


def numeracion(leidos: list[tuple[int | None, float]]) -> tuple[list[int], float] | None:
    """Si las lecturas cuentan 1, 2, 3… hacia abajo, la numeración corregida (y qué tan seguro).

    Una lectura equivocada no rompe la columna: se vota el número de arranque con todas."""
    n = len(leidos)
    votos: dict[int, int] = {}
    for k, (v, _) in enumerate(leidos):
        if v is not None:
            votos[v - k] = votos.get(v - k, 0) + 1
    if not votos:
        return None
    inicio, apoyo = max(votos.items(), key=lambda kv: kv[1])
    if inicio < 1 or apoyo < max(3, 0.6 * n):
        return None
    return [inicio + k for k in range(n)], apoyo / n


def bloques_de_items(gris: np.ndarray, lector, textos: list | None = None) -> list[BloqueItems]:
    """Las columnas de respuestas de la hoja, con su numeración y su encabezado, de izquierda a derecha.

    `lector` lee números impresos (`leer_numero`); `textos` son las líneas del OCR general
    (con `.texto` y `.x0/.y0/.x1/.y1`), para nombrar la sección de cada columna."""
    chicas, ancho, alto, grandes = celdas(gris)
    if not chicas:
        return []
    columnas = [completar_huecos(c, alto) for c in agrupar_columnas(chicas, ancho, alto)]
    etiquetas = []
    for k, col in enumerate(columnas):
        num = numeracion(_numeros_de(col, gris, lector))
        if num is not None:
            etiquetas.append((k, num[0]))
    bloques: list[BloqueItems] = []
    for k, numeros in etiquetas:
        etiqueta = columnas[k]
        vecinas = [
            c
            for c in columnas[k + 1 :]
            if 0.6 * ancho < c.celdas[0].cx - etiqueta.celdas[0].cx < 1.7 * ancho
            and abs(c.celdas[0].cy - etiqueta.celdas[0].cy) < 0.8 * alto
        ]
        if not vecinas:
            continue
        resp = min(vecinas, key=lambda c: abs(c.celdas[0].cx - etiqueta.celdas[0].cx - ancho))
        filas = []
        for c in etiqueta.celdas:
            cerca = min(resp.celdas, key=lambda r: abs(r.cy - c.cy))
            if abs(cerca.cy - c.cy) > 0.7 * alto:  # sin celda de respuesta en esa fila
                cerca = Celda(resp.celdas[0].x0, c.y0, resp.celdas[0].x1, c.y1)
            filas.append(cerca)
        centro = (etiqueta.celdas[0].cx + resp.celdas[0].cx) / 2
        bloques.append(
            BloqueItems(
                _nombre_de_seccion(centro, etiqueta.celdas[0].y0, alto, grandes, textos),
                numeros,
                filas,
            )
        )
    return bloques


def _nombre_de_seccion(
    cx: float, y_tope: int, alto: float, grandes: list[Celda], textos: list | None
) -> str:
    """El título de la sección de esta columna.

    Primero, la celda de encabezado (la celda grande de arriba) que **contiene** la columna; si
    ninguna la contiene, los textos que quedan justo encima y cerca de su centro."""
    if not textos:
        return ""
    contienen = [g for g in grandes if g.x0 <= cx <= g.x1 and g.y1 <= y_tope + alto]
    if contienen:
        g = min(contienen, key=lambda g: abs(y_tope - g.y1))
        dentro = [
            t
            for t in textos
            if g.x0 <= (t.x0 + t.x1) / 2 <= g.x1 and g.y0 <= (t.y0 + t.y1) / 2 <= g.y1
        ]
    else:
        dentro = [
            t
            for t in textos
            if y_tope - 4.5 * alto <= t.cy <= y_tope - 0.3 * alto
            and abs((t.x0 + t.x1) / 2 - cx) < 1.1 * alto * 2
        ]
    dentro.sort(key=lambda t: (round(t.cy / 8), t.x0))
    return " ".join(t.texto.strip() for t in dentro if len(t.texto.strip()) > 1)


# --- plantilla ----------------------------------------------------------------------------------


def _tramos_rectos(filas: list[Celda], ancho: float) -> list[list[int]]:
    """Índices de filas seguidas cuya celda cae a menos de 6 % del ancho de la primera del tramo.

    La tabla del esquema tiene **una** franja x para todas sus filas: en una columna inclinada (la
    foto de una hoja curva) o escalonada, cada tramo recto es su propia tabla y así cada celda
    queda a unos pocos píxeles de donde está de verdad."""
    tramos: list[list[int]] = []
    for k, c in enumerate(filas):
        if tramos and abs(c.cx - filas[tramos[-1][0]].cx) <= 0.06 * ancho:
            tramos[-1].append(k)
        else:
            tramos.append([k])
    return tramos


def _bandas_y(celdas_: list[Celda]) -> list[list[int]]:
    """El tramo vertical de cada fila, sin solaparse con la de arriba (la tabla lo exige)."""
    bandas = [[c.y0, c.y1] for c in celdas_]
    for a, b in pairwise(bandas):
        if b[0] < a[1]:
            medio = (b[0] + a[1]) // 2
            a[1], b[0] = medio, medio
    return bandas


def plantilla_de_digitos(
    img: np.ndarray,
    lector,
    *,
    id: str,
    nombre: str,
    textos: list | None = None,
    digitos: tuple[str, ...] = ("0", "1", "2"),
    primer_item: int = 1,
    primera_columna: int = 0,
    imagen: str | None = None,
) -> tuple[dict, np.ndarray, list[BloqueItems]]:
    """Plantilla (esquema v1) con una tabla de dígitos por columna de respuestas, la referencia con
    las celdas sin lo escrito a mano, y los bloques hallados. Es un borrador: se corrige en el editor."""
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    alto_foto, ancho_foto = gris.shape[:2]
    _, ancho, _, _ = celdas(gris)
    bloques = bloques_de_items(gris, lector, textos)
    tablas: list[dict] = []
    zona = np.zeros_like(gris)
    item = primer_item - 1
    columna = primera_columna - 1  # columna del libro de Excel: una por área (A, B, C…)
    for k, b in enumerate(bloques, start=1):
        seccion = b.seccion or f"Columna {k}"
        if b.numeros[0] == 1 or columna < primera_columna:
            columna += (
                1  # un bloque que vuelve a empezar en 1 es un área nueva; el 31… sigue en la misma
            )
        for tramo in _tramos_rectos(b.filas, ancho):
            fs = [b.filas[i] for i in tramo]
            x0 = int(np.median([c.x0 for c in fs]))
            x1 = int(np.median([c.x1 for c in fs]))
            bandas = _bandas_y(fs)
            filas = []
            for i, banda in zip(tramo, bandas, strict=True):
                item += 1
                filas.append(
                    {
                        "item": item,
                        "texto": f"{seccion} · {b.numeros[i]}",
                        "y": banda,
                        "celda": f"{get_column_letter(columna + 1)}{b.numeros[i]}",
                    }
                )
            tablas.append(
                {
                    "tipo": "digito",
                    "seccion": seccion,
                    "opciones": list(digitos),
                    "columnas_x": [[x0, x1]],
                    "filas": filas,
                }
            )
            for banda in bandas:
                mx, my = round((x1 - x0) * 0.14), round((banda[1] - banda[0]) * 0.14)
                zona[banda[0] + my : banda[1] - my, x0 + mx : x1 - mx] = 255
    # referencia: sin lo escrito a mano dentro de las celdas de respuesta
    tinta = cv2.adaptiveThreshold(
        cv2.GaussianBlur(gris, (0, 0), 1.2),
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        max(31, (min(gris.shape[:2]) // 25) | 1),
        10,
    )
    a_borrar = cv2.dilate(cv2.bitwise_and(tinta, zona), np.ones((3, 3), np.uint8))
    limpia = cv2.inpaint(gris, a_borrar, 3, cv2.INPAINT_TELEA)
    plantilla = {
        "esquema_version": 1,
        "id": id,
        "nombre": nombre,
        "version": 1,
        "paginas": [
            {
                "imagen_referencia": imagen or f"{id}.png",
                "tamano_px": [ancho_foto, alto_foto],
                "tablas": tablas,
            }
        ],
    }
    return plantilla, limpia, bloques
