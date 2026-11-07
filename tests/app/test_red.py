"""AP-R2 / AP-02: elección de la IP local para el QR."""

from autoevalpsi.app import red
from autoevalpsi.app.red import Interfaz, candidatas, elegir_ip, es_privada

WIFI = Interfaz("192.168.1.20", "Wi-Fi", ruta_por_defecto=True)
HYPERV = Interfaz("172.28.96.1", "vEthernet (WSL)")
VBOX = Interfaz("192.168.56.1", "VirtualBox Host-Only Network")
VPN = Interfaz("10.8.0.6", "OpenVPN TAP-Windows")


def test_rangos_privados():
    for ip in ("10.0.0.5", "172.16.0.1", "172.31.255.254", "192.168.0.1"):
        assert es_privada(ip), ip
    for ip in ("127.0.0.1", "169.254.10.2", "172.32.0.1", "100.64.0.1", "8.8.8.8", "::1", "x"):
        assert not es_privada(ip), ip


def test_gana_la_interfaz_con_ruta_por_defecto_aunque_haya_virtuales():
    assert elegir_ip([HYPERV, VBOX, VPN, WIFI]) == "192.168.1.20"
    assert elegir_ip([WIFI, HYPERV, VBOX, VPN]) == "192.168.1.20"


def test_la_ruta_por_defecto_gana_incluso_si_es_un_rango_10():
    casa = Interfaz("10.0.0.7", "Ethernet", ruta_por_defecto=True)
    assert elegir_ip([VBOX, casa]) == "10.0.0.7"


def test_sin_ruta_por_defecto_se_prefiere_no_virtual_y_192_168():
    wifi = Interfaz("192.168.1.20", "Wi-Fi")
    assert elegir_ip([HYPERV, VPN, wifi]) == "192.168.1.20"
    assert elegir_ip([VBOX, wifi]) == "192.168.1.20"  # VirtualBox también es 192.168


def test_sin_nombres_se_prefiere_192_168_sobre_172_y_10():
    # biblioteca estándar: no hay nombres; solo el rango orienta
    sin = [Interfaz("172.28.96.1"), Interfaz("10.8.0.6"), Interfaz("192.168.1.20")]
    assert elegir_ip(sin) == "192.168.1.20"


def test_se_descartan_loopback_link_local_publicas_y_repetidas():
    lista = [
        Interfaz("127.0.0.1"),
        Interfaz("169.254.3.4", "Wi-Fi"),
        Interfaz("8.8.4.4"),
        Interfaz("192.168.1.20", "Wi-Fi"),
        Interfaz("192.168.1.20", "Wi-Fi"),
    ]
    assert [i.ip for i in candidatas(lista)] == ["192.168.1.20"]


def test_sin_red_privada_devuelve_none():
    assert elegir_ip([]) is None
    assert elegir_ip([Interfaz("127.0.0.1"), Interfaz("169.254.1.1")]) is None


def test_la_preferida_manda_si_es_candidata_y_se_ignora_si_no():
    lista = [WIFI, HYPERV]
    assert elegir_ip(lista, "172.28.96.1") == "172.28.96.1"
    assert elegir_ip(lista, "10.9.9.9") == "192.168.1.20"  # no está entre las interfaces
    assert elegir_ip(lista, "8.8.8.8") == "192.168.1.20"  # ni privada


def test_listar_interfaces_con_el_sistema_simulado(monkeypatch):
    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def connect(self, _destino):
            pass

        def getsockname(self):
            return ("192.168.1.20", 5555)

    monkeypatch.setattr(red.socket, "socket", lambda *a, **k: _Socket())
    monkeypatch.setattr(red.socket, "gethostname", lambda: "laptop")
    monkeypatch.setattr(
        red.socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("172.28.96.1", 0)), (2, 1, 6, "", ("192.168.1.20", 0))],
    )
    ifaces = red.listar_interfaces()
    assert {i.ip: i.ruta_por_defecto for i in ifaces} == {
        "172.28.96.1": False,
        "192.168.1.20": True,
    }
    assert elegir_ip(ifaces) == "192.168.1.20"


def test_listar_interfaces_sin_red_no_revienta(monkeypatch):
    def _falla(*a, **k):
        raise OSError("sin red")

    monkeypatch.setattr(red.socket, "socket", _falla)
    monkeypatch.setattr(red.socket, "getaddrinfo", _falla)
    assert red.listar_interfaces() == []
