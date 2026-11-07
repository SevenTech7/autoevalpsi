"""AP-R1: plantillas instaladas en la raíz de la app (PL-D2).

Las plantillas reales viven **fuera del repo**: se importan desde un .zip (el .json de la
plantilla más las imágenes en blanco que cita) y quedan en `<carpeta>/<id>/v<versión>/`. Una
versión instalada no se pisa: una plantilla corregida lleva `version` nueva, porque las
evaluaciones ya guardadas citan la versión con que se leyeron (`BaseDatos.como_evaluacion`).
"""

import io
import re
import shutil
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from autoevalpsi.core.plantilla import Plantilla, PlantillaInvalida, cargar_plantilla
from autoevalpsi.core.registro import RegistroInvalido, cargar_referencia

NOMBRE_JSON = "plantilla.json"
MAX_ARCHIVOS = 100
MAX_DESCOMPRIMIDO = 200 * 1024 * 1024
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class PlantillaNoInstalada(LookupError):
    pass


class ImportacionInvalida(ValueError):
    """El .zip no sirve como plantilla; el mensaje dice por qué, apto para mostrar."""


class PlantillaYaInstalada(ValueError):
    pass


@dataclass(frozen=True)
class PlantillaInstalada:
    plantilla: Plantilla
    ruta: Path  # el plantilla.json instalado


class RepositorioPlantillas:
    def __init__(self, carpeta: str | Path) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._candado = threading.Lock()
        self._referencias: dict[tuple[str, int, int], np.ndarray] = {}

    # --- lectura ------------------------------------------------------------------------

    def listar(self) -> list[PlantillaInstalada]:
        """Todas las versiones instaladas, por id y versión. Las ilegibles se saltan."""
        out = []
        for ruta in self.carpeta.glob(f"*/v*/{NOMBRE_JSON}"):
            try:
                out.append(PlantillaInstalada(cargar_plantilla(ruta), ruta))
            except PlantillaInvalida:
                continue
        return sorted(out, key=lambda i: (i.plantilla.id, i.plantilla.version))

    def obtener(self, id: str, version: int | None = None) -> PlantillaInstalada:
        """La versión pedida o, sin `version`, la más nueva."""
        if not _ID.fullmatch(id):
            raise PlantillaNoInstalada(f"No hay una plantilla «{id}» instalada.")
        candidatas = [i for i in self.listar() if i.plantilla.id == id]
        if version is not None:
            candidatas = [i for i in candidatas if i.plantilla.version == version]
        if not candidatas:
            que = f"«{id}»" if version is None else f"«{id}» versión {version}"
            raise PlantillaNoInstalada(f"No hay una plantilla {que} instalada.")
        return candidatas[-1]

    def referencia(self, inst: PlantillaInstalada, pagina: int) -> np.ndarray:
        """Imagen en blanco (gris) de la página `pagina` (0-based), con caché."""
        clave = (inst.plantilla.id, inst.plantilla.version, pagina)
        with self._candado:
            if clave not in self._referencias:
                self._referencias[clave] = cargar_referencia(
                    inst.ruta, inst.plantilla.paginas[pagina].imagen_referencia
                )
            return self._referencias[clave]

    # --- importación --------------------------------------------------------------------

    def importar_zip(self, datos: bytes) -> PlantillaInstalada:
        """Instala la plantilla de un .zip. Valida todo antes de dejar nada en la carpeta."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(datos))
        except zipfile.BadZipFile as e:
            raise ImportacionInvalida("El archivo no es un .zip válido.") from e
        with zf:
            miembros = [m for m in zf.infolist() if not m.is_dir()]
            if len(miembros) > MAX_ARCHIVOS:
                raise ImportacionInvalida(f"El .zip trae demasiados archivos ({len(miembros)}).")
            if sum(m.file_size for m in miembros) > MAX_DESCOMPRIMIDO:
                raise ImportacionInvalida("El .zip es demasiado grande al descomprimirlo.")
            rutas = {m.filename: self._ruta_segura(m.filename) for m in miembros}
            jsons = [n for n, r in rutas.items() if r.suffix.lower() == ".json"]
            if len(jsons) != 1:
                raise ImportacionInvalida(
                    f"El .zip debe traer un solo archivo .json de plantilla (trae {len(jsons)})."
                )
            base = rutas[jsons[0]].parent

            tmp = self.carpeta / f".importando-{uuid.uuid4().hex}"
            try:
                tmp.mkdir()
                for nombre, ruta in rutas.items():
                    if ruta.parent != base and base not in ruta.parents:
                        continue  # fuera de la carpeta de la plantilla: se ignora
                    destino = tmp / (NOMBRE_JSON if nombre == jsons[0] else ruta.relative_to(base))
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(zf.read(nombre))
                plantilla = self._validar(tmp / NOMBRE_JSON)
                final = self.carpeta / plantilla.id / f"v{plantilla.version}"
                with self._candado:
                    if final.exists():
                        raise PlantillaYaInstalada(
                            f"La plantilla «{plantilla.id}» versión {plantilla.version} ya está "
                            "instalada. Si la corregiste, súbele la versión en el .json."
                        )
                    final.parent.mkdir(parents=True, exist_ok=True)
                    tmp.rename(final)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return PlantillaInstalada(plantilla, final / NOMBRE_JSON)

    @staticmethod
    def _ruta_segura(nombre: str) -> PurePosixPath:
        ruta = PurePosixPath(nombre.replace("\\", "/"))
        if ruta.is_absolute() or ".." in ruta.parts or (ruta.parts and ":" in ruta.parts[0]):
            raise ImportacionInvalida(f"El .zip trae una ruta no permitida: «{nombre}».")
        return ruta

    @staticmethod
    def _validar(json: Path) -> Plantilla:
        try:
            plantilla = cargar_plantilla(json)
        except PlantillaInvalida as e:
            raise ImportacionInvalida(str(e).replace(str(json), "plantilla.json")) from e
        raiz = json.parent.resolve()
        for i, pagina in enumerate(plantilla.paginas):
            imagen = (raiz / pagina.imagen_referencia).resolve()
            if raiz not in imagen.parents:
                raise ImportacionInvalida(
                    f"La imagen de la página {i + 1} apunta fuera de la plantilla: "
                    f"«{pagina.imagen_referencia}»."
                )
            try:
                cargar_referencia(json, pagina.imagen_referencia)
            except RegistroInvalido as e:
                raise ImportacionInvalida(
                    f"Falta o no se lee la imagen en blanco «{pagina.imagen_referencia}» "
                    f"(página {i + 1}) en el .zip."
                ) from e
        return plantilla
