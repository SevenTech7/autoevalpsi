"""AP-R2: URL de captura y QR."""

import io

import cv2
import numpy as np
import segno

from autoevalpsi.app.qr import qr_svg, url_captura

URL = url_captura("192.168.1.20", 8765, "aB3-_xyz0123456789AB")


def test_la_url_lleva_ip_puerto_y_codigo_de_vinculo():
    assert URL == "http://192.168.1.20:8765/captura?vinculo=aB3-_xyz0123456789AB"


def test_el_codigo_se_escapa_en_la_url():
    assert url_captura("10.0.0.2", 80, "a b&c").endswith("?vinculo=a%20b%26c")


def test_el_svg_es_un_svg_sin_cabecera_xml():
    svg = qr_svg(URL)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "<?xml" not in svg


def test_el_qr_decodifica_a_la_url():
    # se rasteriza el mismo QR y se lee con el detector de OpenCV: lo que escanea el celular
    buf = io.BytesIO()
    segno.make(URL, error="m", micro=False).save(buf, kind="png", scale=8, border=4)
    img = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), cv2.IMREAD_GRAYSCALE)
    texto, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    assert texto == URL
