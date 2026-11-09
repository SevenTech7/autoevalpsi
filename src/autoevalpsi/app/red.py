"""AP-R2 / AP-02: qué IP local poner en el QR.

Las laptops tienen adaptadores virtuales (Hyper-V, WSL, VirtualBox, VPN) que también tienen IP
privada; si el QR lleva la equivocada, el celular no conecta. Regla (AP-02): la IP de la
interfaz que tiene la **ruta por defecto** (la que sale a la red de la casa), solo en rangos
privados (RFC 1918); si no se conoce, la mejor candidata por rango y nombre. La usuaria puede
elegir otra de la lista en la pantalla del QR.

Solo biblioteca estándar: nada que instalar. `listar_interfaces()` es lo único que toca la red;
`elegir_ip` y `candidatas` son puras y se prueban con listas simuladas.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass

_PRIVADAS = tuple(
    ipaddress.ip_network(r) for r in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
# Nombres de adaptadores que casi nunca son la red de la casa (cuando el sistema los da).
_VIRTUAL = re.compile(
    r"vethernet|hyper-?v|wsl|virtualbox|vmware|vbox|docker|tap-|vpn|tailscale|zerotier|"
    r"hamachi|loopback|bluetooth|npcap",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Interfaz:
    ip: str
    nombre: str = ""  # vacío si el sistema no lo da (biblioteca estándar)
    ruta_por_defecto: bool = False  # sale por aquí el tráfico a internet


def es_privada(ip: str) -> bool:
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return direccion.version == 4 and any(direccion in red for red in _PRIVADAS)


def _parece_virtual(i: Interfaz) -> bool:
    return bool(_VIRTUAL.search(i.nombre))


def _prioridad(i: Interfaz) -> tuple:
    """Menor = mejor. Ruta por defecto, luego nombre no virtual, luego el rango: las redes de
    casa son casi siempre 192.168.x; Hyper-V/WSL/Docker usan 172.16-31 y las VPN 10.x."""
    rango = 0 if i.ip.startswith("192.168.") else 1 if i.ip.startswith("10.") else 2
    return (not i.ruta_por_defecto, _parece_virtual(i), rango, i.ip)


def candidatas(interfaces: list[Interfaz]) -> list[Interfaz]:
    """Las que sirven para el QR (IPv4 privada, sin repetir), la mejor primero."""
    vistas: dict[str, Interfaz] = {}
    for i in interfaces:
        if es_privada(i.ip) and i.ip not in vistas:
            vistas[i.ip] = i
    return sorted(vistas.values(), key=_prioridad)


def elegir_ip(interfaces: list[Interfaz], preferida: str | None = None) -> str | None:
    """La IP para el QR, o None si no hay ninguna red privada (sin WiFi). `preferida` (la que
    eligió la usuaria) manda si sigue entre las candidatas."""
    lista = candidatas(interfaces)
    if preferida is not None and any(i.ip == preferida for i in lista):
        return preferida
    return lista[0].ip if lista else None


def _ip_de_ruta_por_defecto() -> str | None:
    """IP de la interfaz por la que saldría el tráfico a una dirección externa. UDP `connect`
    solo consulta la tabla de rutas: no envía ningún paquete."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 9))
            return s.getsockname()[0]
    except OSError:
        return None


def listar_interfaces() -> list[Interfaz]:
    ruta = _ip_de_ruta_por_defecto()
    ips: set[str] = set()
    try:
        for *_, direccion in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(str(direccion[0]))
    except OSError:
        pass
    if ruta:
        ips.add(ruta)
    return [Interfaz(ip, ruta_por_defecto=(ip == ruta)) for ip in sorted(ips)]
