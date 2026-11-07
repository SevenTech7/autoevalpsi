"""AP-R0: capa de datos local (SQLite + imágenes)."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest

from autoevalpsi.app.datos import (
    VERSION_ESQUEMA,
    BaseDatos,
    BaseDatosNueva,
    EvaluacionInexistente,
    IdInvalido,
    raiz_por_defecto,
)
from autoevalpsi.core.casillas import ResultadoFila
from autoevalpsi.core.ocr.texto import CampoLeido, ObservacionLeida
from autoevalpsi.core.pipeline import ResultadoProcesamiento, a_evaluacion
from autoevalpsi.core.plantilla import cargar_plantilla

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Reloj:
    """Reloj controlable: cada llamada avanza un segundo."""

    def __init__(self):
        self.t = datetime(2026, 11, 6, 12, 0, 0, tzinfo=UTC)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def bd(tmp_path):
    with BaseDatos(tmp_path / "datos", ahora=Reloj()) as b:
        yield b


def _resultado(sha="a" * 64, pagina=0, items=(1, 2, 3)) -> ResultadoProcesamiento:
    """Ítem 1 verde (B), ítem 2 amarillo (doble marca), ítem 3 verde sin observación."""
    filas = (
        ResultadoFila(1, "B", (0.0, 0.5), ()),
        ResultadoFila(2, None, (0.4, 0.4), ("doble_marca",)),
        ResultadoFila(3, "A", (0.5, 0.0), ()),
    )
    obs = (
        ObservacionLeida(1, "bien", 0.95, True),
        ObservacionLeida(2, "dudo", 0.5, True, ("ocr_confianza_baja",)),
    )
    cab = (
        CampoLeido("paciente", "Ana Perez", 0.9, True),
        CampoLeido("fecha", "5/11", 0.4, True, ("ocr_confianza_baja",)),
    )
    return ResultadoProcesamiento(
        plantilla_id="demo",
        plantilla_version=1,
        pagina=pagina,
        foto_sha256=sha,
        problemas_calidad=("borrosa",),
        registro={"ok": True, "banderas": []},
        filas=tuple(f for f in filas if f.item in items),
        ocr_activo=True,
        observaciones=obs,
        cabecera=cab,
    )


def _crear(bd, **kw):
    kw.setdefault("foto", JPEG)
    kw.setdefault("recortes", {1: np.full((10, 20), 128, np.uint8)})
    return bd.guardar_procesamiento(_resultado(), **kw)


# --- esquema y migraciones -------------------------------------------------------------------


def test_bd_vacia_migra_a_la_version_actual(tmp_path):
    with BaseDatos(tmp_path) as b:
        assert b.version == VERSION_ESQUEMA
    con = sqlite3.connect(tmp_path / "autoevalpsi.db")
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == VERSION_ESQUEMA
        tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert {"evaluaciones", "paginas", "filas", "correcciones", "configuracion"} <= tablas


def test_reabrir_no_repite_migraciones_ni_pierde_datos(tmp_path):
    with BaseDatos(tmp_path) as b:
        b.guardar_configuracion("carpeta_exportacion", "C:/x")
    with BaseDatos(tmp_path) as b:
        assert b.version == VERSION_ESQUEMA
        assert b.leer_configuracion("carpeta_exportacion") == "C:/x"


def test_bd_de_una_version_futura_se_rechaza_sin_tocarla(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    con = sqlite3.connect(tmp_path / "autoevalpsi.db")
    con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA + 1}")
    con.close()
    with pytest.raises(BaseDatosNueva, match="más nueva"):
        BaseDatos(tmp_path)
    con = sqlite3.connect(tmp_path / "autoevalpsi.db")
    try:
        assert con.execute("PRAGMA user_version").fetchone()[0] == VERSION_ESQUEMA + 1
    finally:
        con.close()


def test_raiz_por_defecto_usa_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("AUTOEVALPSI_HOME", raising=False)
    assert raiz_por_defecto() == tmp_path / "AutoEvalPsi"
    monkeypatch.setenv("AUTOEVALPSI_HOME", str(tmp_path / "otra"))
    assert raiz_por_defecto() == tmp_path / "otra"


# --- configuración ---------------------------------------------------------------------------


def test_configuracion_crea_actualiza_y_da_valor_por_defecto(bd):
    assert bd.leer_configuracion("borrar_fotos") is None
    assert bd.leer_configuracion("borrar_fotos", "no") == "no"
    bd.guardar_configuracion("borrar_fotos", "si")
    bd.guardar_configuracion("borrar_fotos", "no")
    assert bd.leer_configuracion("borrar_fotos") == "no"


# --- guardar y leer --------------------------------------------------------------------------


def test_guardar_procesamiento_crea_evaluacion_con_filas(bd):
    ev_id = _crear(bd)
    assert ev_id == "a" * 12  # derivado de la foto, igual que a_evaluacion
    ev = bd.leer_evaluacion(ev_id)
    assert (ev.plantilla_id, ev.plantilla_version, ev.estado) == ("demo", 1, "pendiente")
    assert ev.paciente == "Ana Perez"
    assert ev.cabecera == {"fecha": "5/11"}
    assert [f.item for f in ev.filas] == [1, 2, 3]
    f1, f2, f3 = ev.filas
    assert (f1.opcion_leida, f1.opcion, f1.revisada) == ("B", "B", True)  # verde
    assert (f2.opcion_leida, f2.opcion, f2.revisada) == (None, None, False)  # amarilla
    assert f2.banderas == ("doble_marca", "ocr_confianza_baja")  # casillas + observación
    assert (f2.texto_ocr, f2.observacion) == ("dudo", "dudo")
    assert f3.texto_ocr == "" and f3.revisada
    assert ev.paginas[0].problemas_calidad == ("borrosa",)
    assert ev.paginas[0].foto_ruta is not None


def test_fotos_y_recortes_se_guardan_en_disco_bajo_la_raiz(bd):
    ev = bd.leer_evaluacion(_crear(bd))
    foto = bd.raiz / ev.paginas[0].foto_ruta
    assert foto.read_bytes() == JPEG and foto.suffix == ".jpg"
    recorte = bd.raiz / ev.filas[0].ruta_recorte
    assert cv2.imread(str(recorte), cv2.IMREAD_GRAYSCALE).shape == (10, 20)
    assert ev.filas[1].ruta_recorte is None  # sin recorte guardado
    assert Path(ev.paginas[0].foto_ruta).is_relative_to("fotos")  # rutas relativas a la raíz


def test_foto_png_conserva_su_extension(bd):
    ev = bd.leer_evaluacion(_crear(bd, foto=PNG))
    assert ev.paginas[0].foto_ruta.endswith(".png")


def test_listar_evaluaciones_cuenta_pendientes_y_ordena_recientes_primero(bd):
    a = bd.guardar_procesamiento(_resultado("a" * 64), foto=JPEG)
    b = bd.guardar_procesamiento(_resultado("b" * 64), foto=JPEG)
    lista = bd.listar_evaluaciones()
    assert [e.id for e in lista] == [b, a]
    assert lista[0].filas_pendientes == 1 and lista[0].n_filas == 3


def test_evaluacion_inexistente(bd):
    with pytest.raises(EvaluacionInexistente):
        bd.leer_evaluacion("nada")


def test_segunda_pagina_se_agrega_a_la_misma_evaluacion(bd):
    ev_id = bd.guardar_procesamiento(_resultado("a" * 64, items=(1,)), foto=JPEG)
    seg = _resultado("c" * 64, pagina=1, items=(2, 3))
    assert bd.guardar_procesamiento(seg, foto=PNG, evaluacion_id=ev_id) == ev_id
    ev = bd.leer_evaluacion(ev_id)
    assert [p.pagina for p in ev.paginas] == [0, 1]
    assert [f.item for f in ev.filas] == [1, 2, 3]


def test_misma_pagina_dos_veces_se_rechaza(bd):
    ev_id = _crear(bd)
    with pytest.raises(ValueError, match="página"):
        bd.guardar_procesamiento(_resultado("d" * 64), foto=JPEG, evaluacion_id=ev_id)


def test_repetir_la_misma_foto_no_duplica_la_evaluacion(bd):
    _crear(bd)
    with pytest.raises(ValueError, match="ya existe"):
        _crear(bd)


@pytest.mark.parametrize("malo", ["../x", "a/b", "", "a b", "..", "C:x"])
def test_id_con_caracteres_de_ruta_se_rechaza(bd, malo):
    with pytest.raises(IdInvalido):
        bd.guardar_procesamiento(_resultado(), foto=JPEG, evaluacion_id=malo)


# --- correcciones (AP-05) --------------------------------------------------------------------


def test_cambiar_opcion_confirmada_deja_una_correccion(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 2, opcion="C")
    f = bd.leer_evaluacion(ev_id).filas[1]
    assert (f.opcion_leida, f.opcion, f.revisada) == (None, "C", True)
    [c] = bd.listar_correcciones(ev_id)
    assert (c.item, c.campo, c.antes, c.despues) == (2, "opcion", None, "C")
    assert c.momento.startswith("2026-11-06T12:00:")


def test_cambiar_observacion_deja_una_correccion(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 1, observacion="muy bien")
    [c] = bd.listar_correcciones(ev_id)
    assert (c.item, c.campo, c.antes, c.despues) == (1, "observacion", "bien", "muy bien")
    assert bd.leer_evaluacion(ev_id).filas[0].texto_ocr == "bien"  # lo leído no se pisa


def test_confirmar_sin_cambiar_marca_revisada_y_no_deja_correccion(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 2, opcion=None)  # confirma «sin respuesta» tal cual
    assert bd.leer_evaluacion(ev_id).filas[1].revisada
    assert bd.listar_correcciones(ev_id) == []


def test_repetir_el_mismo_valor_no_agrega_otra_correccion(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 2, opcion="C")
    bd.actualizar_fila(ev_id, 2, opcion="C")
    assert len(bd.listar_correcciones(ev_id)) == 1


def test_cambio_de_opcion_y_observacion_juntos_deja_dos_correcciones(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 2, opcion="A", observacion="")
    assert [c.campo for c in bd.listar_correcciones(ev_id)] == ["opcion", "observacion"]


def test_corregir_una_fila_verde_tambien_se_registra(bd):
    ev_id = _crear(bd)
    bd.actualizar_fila(ev_id, 1, opcion="A")  # la lectura verde estaba mal
    [c] = bd.listar_correcciones(ev_id)
    assert (c.item, c.antes, c.despues) == (1, "B", "A")


def test_fila_inexistente(bd):
    ev_id = _crear(bd)
    with pytest.raises(EvaluacionInexistente):
        bd.actualizar_fila(ev_id, 99, opcion="A")


def test_cambio_de_cabecera_deja_correcciones_sin_item(bd):
    ev_id = _crear(bd)
    bd.actualizar_cabecera(ev_id, paciente="Ana Pérez", cabecera={"fecha": "5/11/2026"})
    ev = bd.leer_evaluacion(ev_id)
    assert ev.paciente == "Ana Pérez" and ev.cabecera == {"fecha": "5/11/2026"}
    cs = {(c.item, c.campo): (c.antes, c.despues) for c in bd.listar_correcciones(ev_id)}
    assert cs == {
        (None, "paciente"): ("Ana Perez", "Ana Pérez"),
        (None, "cabecera.fecha"): ("5/11", "5/11/2026"),
    }


# --- revisión obligatoria (AP-06) ------------------------------------------------------------


def test_pendientes_baja_al_confirmar_y_la_evaluacion_queda_revisada(bd):
    ev_id = _crear(bd)
    assert bd.filas_pendientes(ev_id) == 1
    assert not bd.cabecera_revisada(ev_id)  # la fecha vino con bandera
    bd.actualizar_fila(ev_id, 2, opcion="C")
    assert bd.filas_pendientes(ev_id) == 0
    assert bd.leer_evaluacion(ev_id).estado == "pendiente"  # falta confirmar la cabecera
    bd.confirmar_cabecera(ev_id)
    assert bd.cabecera_revisada(ev_id)
    assert bd.leer_evaluacion(ev_id).estado == "revisada"


def test_cabecera_sin_bandera_nace_revisada(bd):
    res = ResultadoProcesamiento(
        "demo", 1, 0, "e" * 64, (), {"ok": True}, (ResultadoFila(1, "A", (0.5,), ()),)
    )
    ev_id = bd.guardar_procesamiento(res, foto=JPEG)
    assert bd.cabecera_revisada(ev_id)
    assert bd.leer_evaluacion(ev_id).estado == "revisada"


def test_marcar_exportada(bd):
    ev_id = _crear(bd)
    bd.marcar_exportada(ev_id)
    assert bd.leer_evaluacion(ev_id).estado == "exportada"


# --- borrado de fotos (AP-D1) ----------------------------------------------------------------


def test_borrar_fotos_quita_los_archivos_y_conserva_la_lectura(bd):
    ev_id = _crear(bd)
    ev = bd.leer_evaluacion(ev_id)
    foto, recorte = bd.raiz / ev.paginas[0].foto_ruta, bd.raiz / ev.filas[0].ruta_recorte
    assert bd.borrar_fotos(ev_id) == 1
    assert not foto.exists()
    assert recorte.exists()  # los recortes no son «fotos»: siguen para revisar/exportar
    ev = bd.leer_evaluacion(ev_id)
    assert ev.paginas[0].foto_ruta is None and len(ev.filas) == 3
    assert bd.borrar_fotos(ev_id) == 0  # idempotente


def test_borrar_fotos_con_recortes(bd):
    ev_id = _crear(bd)
    recorte = bd.raiz / bd.leer_evaluacion(ev_id).filas[0].ruta_recorte
    bd.borrar_fotos(ev_id, incluir_recortes=True)
    assert not recorte.exists()
    assert bd.leer_evaluacion(ev_id).filas[0].ruta_recorte is None


def test_borrar_fotos_tolera_un_archivo_ya_desaparecido(bd):
    ev_id = _crear(bd)
    (bd.raiz / bd.leer_evaluacion(ev_id).paginas[0].foto_ruta).unlink()
    assert bd.borrar_fotos(ev_id) == 0


# --- puente hacia core.excel -----------------------------------------------------------------


def test_como_evaluacion_usa_lo_confirmado_y_coincide_con_a_evaluacion(bd, lote_sintetico):
    f = lote_sintetico[0]
    plantilla = cargar_plantilla(f.plantilla)
    item = plantilla.paginas[0].tablas[0].filas[0].item
    opciones = plantilla.paginas[0].tablas[0].opciones
    res = ResultadoProcesamiento(
        plantilla.id,
        plantilla.version,
        0,
        "f" * 64,
        (),
        {"ok": True},
        (ResultadoFila(item, opciones[0], (0.5,), ()),),
    )
    ev_id = bd.guardar_procesamiento(res, foto=JPEG, recortes={item: np.zeros((4, 4), np.uint8)})
    bd.actualizar_fila(ev_id, item, opcion=opciones[1], observacion="nota")
    ev = bd.como_evaluacion(ev_id, plantilla, con_recortes=True)
    assert ev.id == ev_id and ev.plantilla is plantilla
    fila = next(x for x in ev.filas if x.item == item)
    assert (fila.opcion, fila.observacion, fila.revisado) == (opciones[1], "nota", True)
    assert isinstance(fila.recorte, np.ndarray)
    sin = bd.como_evaluacion(ev_id, plantilla)
    assert next(x for x in sin.filas if x.item == item).recorte is None
    assert a_evaluacion(res, plantilla, id=ev_id).id == ev_id


def test_como_evaluacion_rechaza_otra_plantilla(bd, lote_sintetico):
    plantilla = cargar_plantilla(lote_sintetico[0].plantilla)
    ev_id = _crear(bd)  # plantilla_id «demo»
    if plantilla.id == "demo":
        pytest.skip("la plantilla de prueba se llama igual")
    with pytest.raises(ValueError, match="plantilla"):
        bd.como_evaluacion(ev_id, plantilla)


def test_los_json_guardados_son_json_valido(bd):
    ev_id = _crear(bd)
    con = sqlite3.connect(bd.raiz / "autoevalpsi.db")
    try:
        for tabla, col in (
            ("filas", "banderas"),
            ("paginas", "registro"),
            ("evaluaciones", "cabecera"),
        ):
            for (v,) in con.execute(f"SELECT {col} FROM {tabla}"):
                json.loads(v)
    finally:
        con.close()
    assert ev_id


def test_evaluacion_de_foto_encuentra_el_id_por_sha(bd):
    assert bd.evaluacion_de_foto("a" * 64) is None
    id = _crear(bd)
    assert bd.evaluacion_de_foto("a" * 64) == id
    assert bd.evaluacion_de_foto("b" * 64) is None
