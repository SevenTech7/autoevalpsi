from tools.sino_desde_foto import LineaCar, construir, encontrar_grupos


def linea(texto: str, x0: int, y0: int, paso: int = 10) -> LineaCar:
    car = [(c, x0 + i * paso) for i, c in enumerate(texto)]
    return LineaCar(texto, x0, y0, x0 + len(texto) * paso, y0 + 20, car)


def test_encuentra_el_si_no_con_la_posicion_de_sus_parentesis():
    ln = linea("Si ( ) No ( )", 100, 50)
    (g,) = encontrar_grupos(ln)
    assert g["si"][0] <= 130 and g["si"][2] >= 150  # los paréntesis del «Sí»
    assert g["no"][0] <= 200 and g["no"][2] >= 220  # y los del «No»
    assert g["si"][2] < g["no"][0]


def test_varios_grupos_en_una_linea_y_texto_pegado_a_la_izquierda():
    ln = linea("1. Martillo Si ( ) No ( ) 2. Corbata Si ( ) No ( )", 0, 50)
    sec = linea("5.2 Lenguaje denominativo", 0, 20)
    plantilla = construir([sec, ln])
    (s,) = plantilla["secciones"]
    assert s["codigo"] == "5.2" and s["titulo"] == "Lenguaje denominativo"
    assert [i["texto"] for i in s["items"]] == ["1. Martillo", "2. Corbata"]


def test_el_texto_de_un_item_puede_estar_en_otra_linea_a_la_izquierda():
    sec = linea("5.3 Lenguaje repetitivo", 0, 20)
    texto = linea("1. Tren", 0, 50)
    marcas = linea("Si ( ) No ( )", 300, 52)
    (s,) = construir([sec, texto, marcas])["secciones"]
    assert s["items"][0]["texto"] == "1. Tren"


def test_la_letra_suelta_del_margen_no_rompe_el_encabezado_y_el_puntaje_se_ubica():
    sec = linea("E 5.5 Lenguaje comprensivo", 5, 20)
    pee = linea("P.E.E. 0/inex", 100, 120)
    (s,) = construir([sec, pee])["secciones"]
    assert s["codigo"] == "5.5" and s["puntaje"] is not None
