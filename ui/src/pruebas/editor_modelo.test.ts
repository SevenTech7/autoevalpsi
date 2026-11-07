import { describe, expect, it } from "vitest";

import type { PaginaDef, PlantillaDef } from "../api/tipos";
import {
  agregarCampoCabecera,
  agregarColumna,
  agregarFila,
  agregarPreguntaSiNo,
  cajaDeCelda,
  moverCabecera,
  moverCelda,
  quitarColumna,
  quitarFila,
  quitarTabla,
  redimensionarCelda,
  renombrarCampoCabecera,
  seleccionValida,
  siguienteItem,
} from "../editor/modelo";

function pagina(): PaginaDef {
  return {
    imagen_referencia: "p.png",
    tamano_px: [1000, 1400],
    cabecera: [{ campo: "paciente", caja: [100, 50, 400, 90], tipo: "texto" }],
    tablas: [
      {
        seccion: "1 Prueba",
        opciones: ["A", "B", "C"],
        columnas_x: [
          [500, 560],
          [600, 660],
          [700, 760],
        ],
        observacion_x: [800, 950],
        filas: [
          { item: 1, texto: "uno", y: [200, 240] },
          { item: 2, texto: "dos", y: [260, 300] },
        ],
      },
    ],
  };
}
const plantilla = (): PlantillaDef => ({
  esquema_version: 1,
  id: "x",
  nombre: "X",
  version: 1,
  omr: { tinta_minima: 0.02, margen_relativo: 0.25 },
  paginas: [pagina()],
});

describe("mover y redimensionar celdas", () => {
  it("mover desplaza su columna y su fila", () => {
    const p = moverCelda(pagina(), 0, 0, 1, 10, 5);
    expect(p.tablas[0]!.columnas_x[1]).toEqual([610, 670]);
    expect(p.tablas[0]!.filas[0]!.y).toEqual([205, 245]);
    expect(p.tablas[0]!.filas[1]!.y).toEqual([260, 300]); // las demás filas no se mueven
  });

  it("no cruza a la vecina ni sale de la imagen", () => {
    const der = moverCelda(pagina(), 0, 0, 1, 500, 0);
    expect(der.tablas[0]!.columnas_x[1]).toEqual([640, 700]); // tope: la columna siguiente
    const arriba = moverCelda(pagina(), 0, 0, 0, -9999, -9999);
    expect(arriba.tablas[0]!.columnas_x[0]![0]).toBeGreaterThanOrEqual(0);
    expect(arriba.tablas[0]!.filas[0]!.y[0]).toBe(0);
    const abajo = moverCelda(pagina(), 0, 1, 0, 0, 9999);
    expect(abajo.tablas[0]!.filas[1]!.y[1]).toBe(1400);
  });

  it("la última columna no pasa a la observación", () => {
    const p = moverCelda(pagina(), 0, 0, 2, 999, 0);
    expect(p.tablas[0]!.columnas_x[2]![1]).toBe(800);
  });

  it("redimensionar respeta el mínimo y a la vecina", () => {
    const a = redimensionarCelda(pagina(), 0, 0, 0, "x1", 100);
    expect(a.tablas[0]!.columnas_x[0]).toEqual([500, 506]);
    const b = redimensionarCelda(pagina(), 0, 0, 0, "x1", 9999);
    expect(b.tablas[0]!.columnas_x[0]![1]).toBe(600);
    const c = redimensionarCelda(pagina(), 0, 1, 0, "y0", 0);
    expect(c.tablas[0]!.filas[1]!.y[0]).toBe(240);
  });

  it("no modifica la página original", () => {
    const original = pagina();
    moverCelda(original, 0, 0, 0, 30, 30);
    expect(original).toEqual(pagina());
  });

  it("la caja de la celda es su columna por su fila", () => {
    expect(cajaDeCelda(pagina(), 0, 1, 2)).toEqual([700, 260, 760, 300]);
  });
});

describe("filas y columnas", () => {
  it("agregar fila: debajo de la última, mismo alto y siguiente ítem", () => {
    const p = agregarFila(plantilla(), 0, 0)!.paginas[0]!;
    expect(p.tablas[0]!.filas[2]).toEqual({ item: 3, texto: "Fila nueva", y: [304, 344] });
  });

  it("agregar fila sin espacio devuelve null", () => {
    const p = plantilla();
    p.paginas[0]!.tablas[0]!.filas[1]!.y = [1370, 1400];
    expect(agregarFila(p, 0, 0)).toBeNull();
  });

  it("quitar la última fila quita la tabla", () => {
    const una = quitarFila(pagina(), 0, 0);
    expect(una.tablas[0]!.filas.map((f) => f.item)).toEqual([2]);
    expect(quitarFila(una, 0, 0).tablas).toHaveLength(0);
  });

  it("agregar columna: a la derecha, mismo ancho, con nombre", () => {
    const sin_obs = pagina();
    sin_obs.tablas[0]!.observacion_x = null;
    const p = agregarColumna(sin_obs, 0)!;
    expect(p.tablas[0]!.columnas_x[3]).toEqual([764, 824]);
    expect(p.tablas[0]!.opciones).toEqual(["A", "B", "C", "Opción 4"]);
  });

  it("agregar columna no invade la observación", () => {
    expect(agregarColumna(pagina(), 0)).toBeNull(); // 764+60 > 800
  });

  it("quitar columna quita también su opción; la única no se puede quitar", () => {
    const p = quitarColumna(pagina(), 0, 1)!;
    expect(p.tablas[0]!.opciones).toEqual(["A", "C"]);
    expect(p.tablas[0]!.columnas_x).toHaveLength(2);
    const sola = pagina();
    sola.tablas[0]!.opciones = ["A"];
    sola.tablas[0]!.columnas_x = [[500, 560]];
    expect(quitarColumna(sola, 0, 0)).toBeNull();
  });
});

describe("preguntas nuevas y tablas", () => {
  it("agrega una tabla Sí/No de una fila, dentro de la imagen y con ítem nuevo", () => {
    const nueva = agregarPreguntaSiNo(plantilla(), 0, [10, 10]);
    const t = nueva.paginas[0]!.tablas[1]!;
    expect(t.opciones).toEqual(["Sí", "No"]);
    expect(t.filas[0]!.item).toBe(3);
    expect(t.columnas_x[0]![0]).toBeGreaterThanOrEqual(0);
    expect(t.columnas_x[0]![1]).toBeLessThanOrEqual(t.columnas_x[1]![0]);
    expect(t.filas[0]!.y[0]).toBeGreaterThanOrEqual(0);
  });

  it("quitar tabla", () => {
    expect(quitarTabla(pagina(), 0).tablas).toHaveLength(0);
  });

  it("siguienteItem mira toda la plantilla", () => {
    expect(siguienteItem(plantilla())).toBe(3);
  });
});

describe("campos de la cabecera", () => {
  it("agregar, rechazar repetidos y vacíos, renombrar", () => {
    const p = agregarCampoCabecera(pagina(), "cargo", [500, 100])!;
    expect(p.cabecera.map((c) => c.campo)).toEqual(["paciente", "cargo"]);
    expect(agregarCampoCabecera(p, "cargo", [0, 0])).toBeNull();
    expect(agregarCampoCabecera(p, "  ", [0, 0])).toBeNull();
    expect(renombrarCampoCabecera(p, 1, "paciente")).toBeNull();
    expect(renombrarCampoCabecera(p, 1, "oficina")!.cabecera[1]!.campo).toBe("oficina");
  });

  it("mover la caja no sale de la imagen", () => {
    const p = moverCabecera(pagina(), 0, -9999, 9999);
    expect(p.cabecera[0]!.caja).toEqual([0, 1360, 300, 1400]);
  });
});

describe("selección", () => {
  it("se anula si ya no existe", () => {
    const p = quitarFila(pagina(), 0, 1);
    expect(seleccionValida(p, { tipo: "celda", tabla: 0, fila: 1, columna: 0 })).toBeNull();
    expect(seleccionValida(p, { tipo: "celda", tabla: 0, fila: 0, columna: 0 })).not.toBeNull();
    expect(seleccionValida(p, { tipo: "cabecera", campo: 3 })).toBeNull();
  });
});
