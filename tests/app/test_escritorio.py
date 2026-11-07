"""AP-R3: arranque/parada del servidor en hilo, instancia única y puente de la ventana.

La ventana real (pywebview) no se prueba aquí: `abrir_ventana` se sustituye."""

import socket
import threading
import urllib.request

import pytest

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.escritorio import (
    CLAVE_CARPETA_EXPORTACION,
    AplicacionYaAbierta,
    ErrorArranque,
    Puente,
    PuertoOcupado,
    ServidorLocal,
    ejecutar,
)
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.servidor import crear_app

TOKEN = "token-de-prueba-0123456789"


@pytest.fixture
def app(tmp_path):
    bd = BaseDatos(tmp_path / "datos")
    yield crear_app(bd, RepositorioPlantillas(tmp_path / "datos" / "plantillas"), token=TOKEN)
    bd.cerrar()


def _salud(puerto: int) -> bytes:
    with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=2) as r:
        return r.read()


def test_arranca_responde_y_se_detiene(app):
    srv = ServidorLocal(app, puerto=0)
    srv.iniciar()
    try:
        assert srv.puerto > 0
        assert srv.ips_escuchadas == ["127.0.0.1"]
        assert b'"ok":true' in _salud(srv.puerto).replace(b" ", b"")
    finally:
        srv.detener()
    with pytest.raises(OSError):
        _salud(srv.puerto)


def test_el_hilo_termina_al_detener(app):
    antes = threading.active_count()
    srv = ServidorLocal(app, puerto=0)
    srv.iniciar()
    assert threading.active_count() > antes
    srv.detener()
    assert threading.active_count() <= antes + 1  # tolera hilos auxiliares del cliente HTTP


def test_la_api_sigue_exigiendo_el_token(app):
    srv = ServidorLocal(app, puerto=0)
    srv.iniciar()
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{srv.puerto}/api/evaluaciones", timeout=2)
        assert e.value.code in (401, 403)
    finally:
        srv.detener()


def test_segunda_instancia_se_avisa_como_ya_abierta(app, tmp_path):
    primera = ServidorLocal(app, puerto=0)
    primera.iniciar()
    try:
        bd2 = BaseDatos(tmp_path / "otra")
        app2 = crear_app(bd2, RepositorioPlantillas(tmp_path / "otra" / "p"), token=TOKEN)
        with pytest.raises(AplicacionYaAbierta) as e:
            ServidorLocal(app2, puerto=primera.puerto).iniciar()
        assert "ya está abierta" in str(e.value)
        bd2.cerrar()
        assert b"ok" in _salud(primera.puerto)  # la primera no se vio afectada
    finally:
        primera.detener()


def test_puerto_ocupado_por_otro_programa(app):
    intruso = socket.socket()
    intruso.bind(("127.0.0.1", 0))
    intruso.listen()
    try:
        puerto = intruso.getsockname()[1]
        with pytest.raises(PuertoOcupado) as e:
            ServidorLocal(app, puerto=puerto).iniciar()
        assert str(puerto) in str(e.value)
    finally:
        intruso.close()


def test_ip_que_no_existe_no_tumba_el_arranque(app):
    srv = ServidorLocal(app, puerto=0, ips=["203.0.113.77"])  # no es de esta máquina
    srv.iniciar()
    try:
        assert srv.ips_escuchadas == ["127.0.0.1"]
        assert b"ok" in _salud(srv.puerto)
    finally:
        srv.detener()


def test_no_escucha_en_todas_las_interfaces(app):
    srv = ServidorLocal(app, puerto=0)
    srv.iniciar()
    try:
        assert all(s.getsockname()[0] != "0.0.0.0" for s in srv._sockets)
    finally:
        srv.detener()


def test_puente_guarda_la_carpeta_elegida(tmp_path):
    with BaseDatos(tmp_path) as bd:
        pedidas = []

        def dialogo(inicial):
            pedidas.append(inicial)
            return str(tmp_path / "salida")

        puente = Puente(bd, dialogo)
        assert puente.elegir_carpeta_exportacion() == str(tmp_path / "salida")
        assert bd.leer_configuracion(CLAVE_CARPETA_EXPORTACION) == str(tmp_path / "salida")
        puente.elegir_carpeta_exportacion()
        assert pedidas == ["", str(tmp_path / "salida")]  # la segunda vez abre donde quedó


def test_puente_cancelar_no_cambia_nada(tmp_path):
    with BaseDatos(tmp_path) as bd:
        bd.guardar_configuracion(CLAVE_CARPETA_EXPORTACION, "C:/vieja")
        assert Puente(bd, lambda _i: None).elegir_carpeta_exportacion() is None
        assert bd.leer_configuracion(CLAVE_CARPETA_EXPORTACION) == "C:/vieja"


def test_puente_abre_solo_carpetas_que_existen(tmp_path):
    abiertas = []
    with BaseDatos(tmp_path) as bd:
        puente = Puente(bd, lambda _i: None, abrir=abiertas.append)
        assert puente.abrir_carpeta(str(tmp_path)) is True
        assert abiertas == [tmp_path]
        archivo = tmp_path / "x.xlsx"
        archivo.write_bytes(b"")
        assert puente.abrir_carpeta(str(archivo)) is False  # un archivo no se ejecuta
        assert puente.abrir_carpeta(str(tmp_path / "no_existe")) is False
        assert puente.abrir_carpeta("") is False
        assert abiertas == [tmp_path]


def test_puente_abrir_carpeta_no_revienta_si_el_sistema_falla(tmp_path):
    def falla(_c):
        raise OSError("sin explorador")

    with BaseDatos(tmp_path) as bd:
        assert Puente(bd, lambda _i: None, abrir=falla).abrir_carpeta(str(tmp_path)) is False


def test_ejecutar_abre_la_ventana_con_el_token_y_cierra_todo(tmp_path):
    vistas = []

    def ventana(url, bd):
        vistas.append(url)
        puerto = int(url.split(":")[2].split("/")[0])
        assert b"ok" in _salud(puerto)  # el servidor ya responde cuando se abre la ventana

    assert ejecutar(raiz=tmp_path, puerto=0, ventana=ventana) == 0
    assert len(vistas) == 1 and "?token=" in vistas[0] and vistas[0].startswith("http://127.0.0.1:")
    puerto = int(vistas[0].split(":")[2].split("/")[0])
    with pytest.raises(OSError):
        _salud(puerto)  # servidor cerrado


def test_ejecutar_muestra_el_error_de_instancia_ya_abierta(tmp_path, app):
    primera = ServidorLocal(app, puerto=0)
    primera.iniciar()
    mensajes = []
    try:
        codigo = ejecutar(
            raiz=tmp_path,
            puerto=primera.puerto,
            ventana=lambda *_: pytest.fail("no debe abrir otra ventana"),
            mostrar_error=mensajes.append,
        )
    finally:
        primera.detener()
    assert codigo == 2
    assert mensajes and "ya está abierta" in mensajes[0]


def test_ejecutar_cierra_el_servidor_si_la_ventana_falla(tmp_path):
    puertos = []

    def ventana(url, bd):
        puertos.append(int(url.split(":")[2].split("/")[0]))
        raise ErrorArranque("falló la ventana")

    mensajes = []
    assert ejecutar(raiz=tmp_path, puerto=0, ventana=ventana, mostrar_error=mensajes.append) == 2
    with pytest.raises(OSError):
        _salud(puertos[0])
