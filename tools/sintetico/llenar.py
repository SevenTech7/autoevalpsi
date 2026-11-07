"""BS-R1: llena el formulario sintético y devuelve la verdad de terreno.

Verdad de terreno (dict serializable a JSON):
  plantilla, tinta ("azul"|"negra"),
  cabecera: {campo: texto},
  items: {"<item>": {"caso", "estilo", "marcas": [opciones marcadas], "tachada"?, "observacion"}}

Casos: normal · vacia (sin marca) · doble (dos opciones) · tachon (una opción tachada y la
válida en otra) · fuera (la marca desborda la celda) · tenue (tinta muy clara).
`marcas` es la lectura correcta: [] en `vacia`, dos opciones en `doble`, la válida en `tachon`.
"""

from collections.abc import Mapping

import cv2
import numpy as np

from autoevalpsi.core.plantilla import Plantilla

CASOS = ("normal", "vacia", "doble", "tachon", "fuera", "tenue")
_PESOS = (0.66, 0.09, 0.07, 0.06, 0.06, 0.06)
ESTILOS = ("X", "check", "circulo", "relleno")
TINTAS = {"azul": (170, 70, 20), "negra": (35, 35, 35)}  # BGR
_PALABRAS = (
    "buen", "animo", "duerme", "poco", "se", "enoja", "mucho", "come", "bien", "triste",
    "casi", "nunca", "juega", "con", "amigos", "llora", "a", "veces", "tranquilo", "cansado",
)  # fmt: skip
_NOMBRES = ("Maria Quispe", "Juan Perez", "Ana Mamani", "Luis Flores", "Rosa Condori", "Pedro Rios")
UMBRAL_TINTA = 25
_SCRIPT = cv2.FONT_HERSHEY_SCRIPT_COMPLEX


def _marca(img, centro, mitad, estilo, color, rng, grosor, alfa=1.0):
    """Dibuja una marca sobre `img` (BGR) trabajando en un recorte para no copiar toda la hoja."""
    cx, cy = centro
    r = int(mitad * 1.5) + 20
    x0, y0 = max(cx - r, 0), max(cy - r, 0)
    x1, y1 = min(cx + r, img.shape[1]), min(cy + r, img.shape[0])
    roi = img[y0:y1, x0:x1].copy()
    capa = roi.copy()
    c = (cx - x0, cy - y0)
    m = mitad

    def j(a):
        return int(rng.uniform(-a, a) * m)

    if estilo == "X":
        cv2.line(
            capa,
            (c[0] - m + j(0.12), c[1] - m + j(0.12)),
            (c[0] + m + j(0.12), c[1] + m + j(0.12)),
            color, grosor, cv2.LINE_AA,
        )  # fmt: skip
        cv2.line(
            capa,
            (c[0] + m + j(0.12), c[1] - m + j(0.12)),
            (c[0] - m + j(0.12), c[1] + m + j(0.12)),
            color, grosor, cv2.LINE_AA,
        )  # fmt: skip
    elif estilo == "check":
        pts = np.array(
            [
                (c[0] - m, c[1] + j(0.1)),
                (c[0] - m * 0.3 + j(0.1), c[1] + m * 0.8),
                (c[0] + m, c[1] - m * 0.9 + j(0.1)),
            ],
            np.int32,
        )
        cv2.polylines(capa, [pts], False, color, grosor, cv2.LINE_AA)
    elif estilo == "circulo":
        ini = float(rng.uniform(0, 360))
        cv2.ellipse(
            capa, c, (m, int(m * 0.9)), float(rng.uniform(-20, 20)), ini, ini + 340,
            color, grosor, cv2.LINE_AA,
        )  # fmt: skip
    else:  # relleno
        cv2.ellipse(capa, c, (int(m * 0.7), int(m * 0.7)), 0, 0, 360, color, -1, cv2.LINE_AA)
    img[y0:y1, x0:x1] = cv2.addWeighted(capa, alfa, roi, 1 - alfa, 0)


def _tachon(img, centro, mitad, color, rng, grosor):
    cx, cy = centro
    pts = []
    n = int(rng.integers(6, 9))
    for k in range(n):
        x = cx + (mitad * 1.1 if k % 2 else -mitad * 1.1)
        y = cy - mitad * 0.9 + (k / (n - 1)) * mitad * 1.8
        pts.append((int(x + rng.uniform(-4, 4)), int(y + rng.uniform(-4, 4))))
    cv2.polylines(img, [np.array(pts, np.int32)], False, color, grosor, cv2.LINE_AA)


def _texto_manuscrito(img, caja, texto, color, rng):
    x0, y0, x1, y1 = caja
    escala = 1.6
    while True:
        (w, h), _ = cv2.getTextSize(texto, _SCRIPT, escala, 2)
        if (w <= x1 - x0 - 30 and h <= y1 - y0 - 40) or escala <= 0.4:
            break
        escala -= 0.1
    origen = (x0 + 15 + int(rng.integers(0, 10)), (y0 + y1 + h) // 2 + int(rng.integers(-6, 7)))
    cv2.putText(img, texto, origen, _SCRIPT, escala, color, int(rng.integers(2, 4)), cv2.LINE_AA)


def llenar(
    blanca: np.ndarray,
    plantilla: Plantilla,
    rng: np.random.Generator,
    *,
    casos: Mapping[int, str] | None = None,
    tinta: str | None = None,
) -> tuple[np.ndarray, dict]:
    """Devuelve (hoja llena BGR, verdad). `casos` fuerza el caso de ciertos ítems."""
    img = cv2.cvtColor(blanca, cv2.COLOR_GRAY2BGR)
    tinta = tinta or str(rng.choice(list(TINTAS)))
    color = TINTAS[tinta]
    pagina = plantilla.paginas[0]
    verdad: dict = {"plantilla": plantilla.id, "tinta": tinta, "cabecera": {}, "items": {}}

    textos = {
        "paciente": str(rng.choice(_NOMBRES)),
        "fecha": f"{rng.integers(1, 29):02d}/{rng.integers(1, 13):02d}/2026",
    }
    for c in pagina.cabecera:
        x0, _y0, _x1, y1 = c.caja
        texto = textos.get(c.campo, "dato")
        verdad["cabecera"][c.campo] = texto
        cv2.putText(img, texto, (x0 + 15, y1 - 22), _SCRIPT, 1.6, color, 3, cv2.LINE_AA)

    for tabla in pagina.tablas:
        opciones = tabla.opciones
        ancho_col = tabla.columnas_x[0][1] - tabla.columnas_x[0][0]
        for fila in tabla.filas:
            caso = (casos or {}).get(fila.item) or str(rng.choice(CASOS, p=_PESOS))
            if caso not in CASOS:
                raise ValueError(f"caso desconocido: {caso}")
            estilo = str(rng.choice(ESTILOS))
            yc = (fila.y[0] + fila.y[1]) // 2
            elegidas = [int(k) for k in rng.permutation(len(opciones))[:2]]

            def centro(k, extra=6, yc=yc, tabla=tabla):
                xa, xb = tabla.columnas_x[k]
                return (
                    (xa + xb) // 2 + int(rng.integers(-extra, extra + 1)),
                    yc + int(rng.integers(-extra, extra + 1)),
                )

            grosor = int(rng.integers(5, 8))
            mitad = int(rng.uniform(0.28, 0.38) * ancho_col)
            item: dict = {"caso": caso, "estilo": estilo, "marcas": []}
            if caso == "doble":
                for k in sorted(elegidas):
                    _marca(img, centro(k), mitad, estilo, color, rng, grosor)
                item["marcas"] = [opciones[k] for k in sorted(elegidas)]
            elif caso == "tachon":
                mala, buena = elegidas
                _marca(img, centro(mala), mitad, estilo, color, rng, grosor)
                _tachon(img, centro(mala, 0), mitad, color, rng, grosor)
                _marca(img, centro(buena), mitad, estilo, color, rng, grosor)
                item["marcas"] = [opciones[buena]]
                item["tachada"] = opciones[mala]
            elif caso == "fuera":
                k = elegidas[0]
                grande = int(rng.uniform(0.55, 0.65) * ancho_col)
                if estilo == "relleno":
                    grande = int(grande * 1.4)  # el relleno dibuja 0.7 * mitad
                _marca(img, centro(k, 12), grande, estilo, color, rng, grosor)
                item["marcas"] = [opciones[k]]
            elif caso in ("normal", "tenue"):
                k = elegidas[0]
                alfa = float(rng.uniform(0.35, 0.5)) if caso == "tenue" else 1.0
                _marca(img, centro(k), mitad, estilo, color, rng, grosor, alfa)
                item["marcas"] = [opciones[k]]

            item["observacion"] = ""
            if tabla.observacion_x and rng.random() < 0.5:
                palabras = rng.choice(_PALABRAS, int(rng.integers(1, 4)))
                item["observacion"] = " ".join(str(p) for p in palabras)
                caja = [tabla.observacion_x[0], fila.y[0], tabla.observacion_x[1], fila.y[1]]
                _texto_manuscrito(img, caja, item["observacion"], color, rng)
            verdad["items"][str(fila.item)] = item
    return img, verdad


def fraccion_tinta(blanca: np.ndarray, llena: np.ndarray, caja: list[int]) -> float:
    """Fracción de píxeles de `caja` más oscuros en `llena` que en `blanca` (medida de tinta)."""
    x0, y0, x1, y1 = caja
    gris = cv2.cvtColor(llena, cv2.COLOR_BGR2GRAY) if llena.ndim == 3 else llena
    dif = blanca[y0:y1, x0:x1].astype(np.int16) - gris[y0:y1, x0:x1].astype(np.int16)
    return float((dif > UMBRAL_TINTA).mean())
