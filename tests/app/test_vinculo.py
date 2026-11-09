"""AP-D2: vínculo del celular — un solo celular, reemplazable, con alcance acotado."""

import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.datos import _MIGRACIONES, VERSION_ESQUEMA, BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.red import Interfaz
from autoevalpsi.app.servidor import crear_app
from autoevalpsi.app.vinculo import Vinculos

TOKEN = "token-de-prueba-0123456789"
LAPTOP = ("127.0.0.1", 50000)
CELULAR_A = ("192.168.1.50", 40000)
CELULAR_B = ("192.168.1.51", 40001)
WIFI = Interfaz("192.168.1.20", "Wi-Fi", ruta_por_defecto=True)


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(scope="module")
def zip_plantilla(lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    imagen = datos["paginas"][0]["imagen_referencia"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plantilla.json", (carpeta / "plantilla.json").read_bytes())
        zf.writestr(imagen, (carpeta / "blanca.png").read_bytes())
    return buf.getvalue()


@pytest.fixture
def entorno(tmp_path, zip_plantilla):
    bd = BaseDatos(tmp_path / "datos")
    plantillas = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    app = crear_app(bd, plantillas, token=TOKEN, interfaces=lambda: [WIFI])
    with (
        TestClient(app, headers={"X-Token": TOKEN}, client=LAPTOP) as laptop,
        TestClient(app, client=CELULAR_A) as celular,
        TestClient(app, client=CELULAR_B) as otro,
    ):
        yield laptop, celular, otro, app, bd
    bd.cerrar()


def _codigo(laptop) -> str:
    return laptop.post("/api/vinculo/iniciar").json()["url"].split("vinculo=")[1]


def _vincular(laptop, celular) -> str:
    r = celular.post("/api/vinculo", json={"codigo": _codigo(laptop)})
    assert r.status_code == 200, r.text
    return r.json()["dispositivo"]


def _cod(r) -> str:
    return r.json()["detail"]["codigo"]


# --- el código ---------------------------------------------------------------------------------


def test_el_codigo_canjeado_da_una_credencial_y_queda_vinculado(entorno):
    laptop, celular, _, _, bd = entorno
    assert laptop.get("/api/vinculo").json()["vinculado"] is False
    credencial = _vincular(laptop, celular)
    assert len(credencial) >= 43  # 256 bits en base64
    estado = laptop.get("/api/vinculo").json()
    assert estado["vinculado"] is True and estado["creado"]
    # en la base solo queda la huella, nunca la credencial
    assert credencial not in bd.leer_dispositivo().huella


def test_un_codigo_usado_dos_veces_se_rechaza(entorno):
    laptop, celular, otro, *_ = entorno
    codigo = _codigo(laptop)
    assert celular.post("/api/vinculo", json={"codigo": codigo}).status_code == 200
    r = otro.post("/api/vinculo", json={"codigo": codigo})
    assert r.status_code == 403 and _cod(r) == "codigo_invalido"


def test_un_codigo_inventado_se_rechaza_y_no_gasta_el_pendiente(entorno):
    laptop, celular, otro, *_ = entorno
    codigo = _codigo(laptop)
    assert otro.post("/api/vinculo", json={"codigo": "adivinando"}).status_code == 403
    assert celular.post("/api/vinculo", json={"codigo": codigo}).status_code == 200


def test_pedir_otro_codigo_anula_el_anterior(entorno):
    laptop, celular, *_ = entorno
    viejo = _codigo(laptop)
    nuevo = _codigo(laptop)
    assert celular.post("/api/vinculo", json={"codigo": viejo}).status_code == 403
    assert celular.post("/api/vinculo", json={"codigo": nuevo}).status_code == 200


def test_un_codigo_vencido_se_rechaza(tmp_path):
    reloj = Reloj()
    with BaseDatos(tmp_path) as bd:
        v = Vinculos(bd, reloj=reloj, vencimiento=300)
        codigo = v.iniciar().codigo
        reloj.t += 301
        assert v.canjear(codigo) is None and not v.vinculado
        codigo = v.iniciar().codigo
        reloj.t += 299
        assert v.canjear(codigo) is not None and v.vinculado


def test_el_codigo_no_se_acepta_sin_haberlo_pedido(entorno):
    _, celular, *_ = entorno
    assert celular.post("/api/vinculo", json={"codigo": ""}).status_code == 403
    assert celular.post("/api/vinculo", json={}).status_code == 422


# --- quién puede pedir códigos -----------------------------------------------------------------


def test_desde_otra_ip_no_se_pueden_pedir_codigos_ni_con_el_token(entorno):
    _, celular, *_ = entorno
    r = celular.post("/api/vinculo/iniciar", headers={"X-Token": TOKEN})
    assert r.status_code == 403 and _cod(r) == "solo_laptop"


def test_en_la_laptop_pedir_un_codigo_exige_el_token(entorno):
    _, _, _, app, _ = entorno
    with TestClient(app, client=LAPTOP) as sin_token:
        r = sin_token.post("/api/vinculo/iniciar")
    assert r.status_code == 401 and _cod(r) == "sin_token"


def test_el_token_por_query_tampoco_vale_desde_otra_ip(entorno):
    _, celular, *_ = entorno
    assert celular.get(f"/api/evaluaciones?token={TOKEN}").status_code == 403


# --- la credencial y su alcance ----------------------------------------------------------------


def test_la_credencial_abre_fotos_cola_y_plantillas(entorno, lote_sintetico):
    laptop, celular, *_ = entorno
    credencial = _vincular(laptop, celular)
    h = {"X-Dispositivo": credencial}
    plantillas = celular.get("/api/plantillas", headers=h)
    assert plantillas.status_code == 200
    pid = plantillas.json()[0]["id"]
    # la definición completa del formulario no la necesita el celular
    assert celular.get(f"/api/plantillas/{pid}", headers=h).status_code == 403
    assert celular.get("/api/cola", headers=h).status_code == 200
    r = celular.post(
        "/api/fotos",
        data={"plantilla": pid},
        files={"foto": ("f.jpg", lote_sintetico[0].foto.read_bytes(), "image/jpeg")},
        headers=h,
    )
    assert r.status_code == 202, r.text
    assert celular.get(f"/api/cola/{r.json()['trabajo']['id']}", headers=h).status_code == 200


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("GET", "/api/evaluaciones"),
        ("GET", "/api/evaluaciones/x"),
        ("PUT", "/api/evaluaciones/x"),
        ("POST", "/api/evaluaciones/x/exportar"),
        ("POST", "/api/plantillas/importar"),
        ("GET", "/api/plantillas/x"),
        ("GET", "/api/plantillas/x/referencia/0"),
        ("GET", "/api/plantillas/x/libro/comprobacion"),
        ("POST", "/api/vinculo/iniciar"),
        ("GET", "/api/vinculo"),
        ("DELETE", "/api/vinculo"),
    ],
)
def test_la_credencial_no_abre_las_rutas_de_administracion(entorno, metodo, ruta):
    laptop, celular, *_ = entorno
    h = {"X-Dispositivo": _vincular(laptop, celular)}
    r = celular.request(metodo, ruta, headers=h)
    assert r.status_code == 403 and _cod(r) == "solo_laptop"


def test_una_credencial_ajena_es_403_y_no_se_lee_el_cuerpo(entorno, lote_sintetico):
    laptop, celular, otro, _, bd = entorno
    _vincular(laptop, celular)
    r = otro.post(
        "/api/fotos",
        data={"plantilla": "x"},
        files={"foto": ("f.jpg", lote_sintetico[0].foto.read_bytes())},
        headers={"X-Dispositivo": "credencial-ajena"},
    )
    assert r.status_code == 403 and _cod(r) == "dispositivo_no_vinculado"
    assert bd.listar_evaluaciones() == []


def test_sin_credencial_se_pide_vincular(entorno):
    _, celular, *_ = entorno
    r = celular.get("/api/plantillas")
    assert r.status_code == 401 and _cod(r) == "sin_credencial"


def test_la_credencial_en_la_url_no_sirve(entorno):
    laptop, celular, *_ = entorno
    credencial = _vincular(laptop, celular)
    assert celular.get(f"/api/plantillas?dispositivo={credencial}").status_code == 401


def test_la_credencial_no_vale_en_la_laptop_sin_token(entorno):
    laptop, celular, _, app, _ = entorno
    credencial = _vincular(laptop, celular)
    with TestClient(app, client=LAPTOP) as sin_token:
        r = sin_token.get("/api/plantillas", headers={"X-Dispositivo": credencial})
    assert r.status_code == 401


def test_la_pagina_y_la_salud_siguen_abiertas(entorno):
    _, celular, *_ = entorno
    assert celular.get("/captura").status_code == 200
    assert celular.get("/api/salud").json()["ok"] is True


# --- reemplazo y desvinculación ---------------------------------------------------------------


def test_vincular_un_segundo_celular_reemplaza_al_primero(entorno):
    laptop, celular, otro, *_ = entorno
    primera = _vincular(laptop, celular)
    segunda = _vincular(laptop, otro)
    assert primera != segunda
    assert celular.get("/api/plantillas", headers={"X-Dispositivo": primera}).status_code == 403
    assert otro.get("/api/plantillas", headers={"X-Dispositivo": segunda}).status_code == 200


def test_desvincular_cancela_la_credencial(entorno):
    laptop, celular, *_ = entorno
    h = {"X-Dispositivo": _vincular(laptop, celular)}
    assert laptop.delete("/api/vinculo").json() == {"desvinculado": True}
    assert celular.get("/api/plantillas", headers=h).status_code == 403
    assert laptop.get("/api/vinculo").json()["vinculado"] is False
    assert laptop.delete("/api/vinculo").json() == {"desvinculado": False}


def test_el_vinculo_sobrevive_al_reinicio_de_la_app(tmp_path, zip_plantilla):
    raiz = tmp_path / "datos"
    with BaseDatos(raiz) as bd:
        v = Vinculos(bd)
        credencial = v.canjear(v.iniciar().codigo)
    with BaseDatos(raiz) as bd:
        reabierto = Vinculos(bd)
        assert reabierto.vinculado and reabierto.credencial_valida(credencial)
        assert not reabierto.credencial_valida("otra")


def test_el_ultimo_uso_se_anota_sin_escribir_en_cada_peticion(tmp_path):
    reloj = Reloj()
    with BaseDatos(tmp_path) as bd:
        v = Vinculos(bd, reloj=reloj)
        credencial = v.canjear(v.iniciar().codigo)
        assert bd.leer_dispositivo().ultimo_uso is None
        assert v.credencial_valida(credencial)
        primero = bd.leer_dispositivo().ultimo_uso
        assert primero is not None


# --- esquema v2 ----------------------------------------------------------------------------------


def test_una_bd_v1_migra_a_v2_sin_perder_datos(tmp_path):
    raiz = tmp_path / "vieja"
    raiz.mkdir()
    con = sqlite3.connect(raiz / "autoevalpsi.db")
    for sentencia in _MIGRACIONES[0]:
        con.execute(sentencia)
    con.execute("INSERT INTO configuracion(clave, valor) VALUES ('carpeta_exportacion', 'C:/x')")
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()
    assert VERSION_ESQUEMA == 2
    with BaseDatos(raiz) as bd:
        assert bd.version == 2
        assert bd.leer_configuracion("carpeta_exportacion") == "C:/x"
        assert bd.leer_dispositivo() is None
        bd.guardar_dispositivo("h1")
        bd.guardar_dispositivo("h2")  # un solo registro: el segundo reemplaza al primero
        assert bd.leer_dispositivo().huella == "h2"
        assert bd.borrar_dispositivo() is True


def test_la_tabla_de_dispositivos_solo_admite_un_registro(tmp_path):
    with BaseDatos(tmp_path) as bd:
        bd.guardar_dispositivo("h")
    con = sqlite3.connect(tmp_path / "autoevalpsi.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO dispositivos(id, huella, creado) VALUES (2, 'x', 'y')")
    finally:
        con.close()
