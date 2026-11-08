import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Plantilla } from "../api/tipos";
import { Revision, describirBandera, hayObservaciones } from "../pantallas/Revision";
import { clienteFalso, evaluacion, fila } from "./datos";
import { render } from "./render";

afterEach(() => vi.restoreAllMocks());

function plantillaDeNumeros(): Plantilla {
  return {
    id: "vineland",
    nombre: "Vineland",
    version: 1,
    paginas: [
      {
        cabecera: [{ campo: "paciente" }],
        tablas: [
          {
            tipo: "digito",
            opciones: ["0", "1", "2"],
            filas: [
              { item: 1, texto: "Ítem 1" },
              { item: 2, texto: "Ítem 2" },
              { item: 3, texto: "Ítem 3" },
            ],
          },
        ],
      },
    ],
  };
}

function evaluacionDeNumeros() {
  return evaluacion({
    plantilla_id: "vineland",
    cabecera_revisada: true,
    filas: [
      fila({ item: 1, opcion: "2", opcion_leida: "2", revisada: false, ruta_recorte: "recortes/ev1/item_1.png" }),
      fila({
        item: 2,
        opcion: "1",
        opcion_leida: "1",
        banderas: ["ocr_digito_dudoso"],
        revisada: false,
        ruta_recorte: "recortes/ev1/item_2.png",
      }),
      fila({ item: 3, opcion: null, opcion_leida: null, banderas: ["celda_vacia"], revisada: false }),
    ],
    filas_pendientes: 3,
  });
}

function montar(corregirEvaluacion = vi.fn()) {
  const api = clienteFalso({ corregirEvaluacion });
  render(
    <Revision
      api={api}
      evaluacion={evaluacionDeNumeros()}
      plantilla={plantillaDeNumeros()}
      alActualizar={vi.fn()}
      alDescartar={vi.fn()}
    />,
  );
  return api;
}

const filaDe = (item: number) => document.querySelector<HTMLElement>(`[data-item="${item}"]`)!;

describe("revisión de números manuscritos", () => {
  it("muestra el número como opción, lo escrito (la celda) y avisa lo dudoso y lo vacío", () => {
    montar();
    expect(screen.getByRole("columnheader", { name: "Lo escrito" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Observación" })).not.toBeInTheDocument();
    expect(within(filaDe(1)).getByAltText("Lo escrito en el ítem 1")).toBeInTheDocument();
    expect(within(filaDe(3)).getByText("vacía")).toBeInTheDocument();
    expect(within(filaDe(1)).getByRole("radio", { name: "2" })).toBeChecked();
    // los avisos tienen su palabra
    expect(describirBandera("celda_vacia")).toBe("La celda está vacía");
    expect(describirBandera("ocr_digito_dudoso")).toBe("El número se lee dudoso");
    expect(within(filaDe(3)).getByText("La celda está vacía")).toBeInTheDocument();
  });

  it("la tecla es el número mismo (no la posición de la opción)", () => {
    montar();
    userEvent.click(filaDe(1));
    fireEvent.keyDown(window, { key: "0" });
    expect(within(filaDe(1)).getByRole("radio", { name: "0" })).toBeChecked();
    fireEvent.keyDown(window, { key: "2" });
    expect(within(filaDe(1)).getByRole("radio", { name: "2" })).toBeChecked();
    fireEvent.keyDown(window, { key: "7" }); // no es una opción: no cambia nada
    expect(within(filaDe(1)).getByRole("radio", { name: "2" })).toBeChecked();
  });

  it("Borrar deja la celda sin respuesta", () => {
    montar();
    fireEvent.keyDown(window, { key: "Backspace" });
    expect(within(filaDe(1)).getByRole("radio", { name: "Sin respuesta" })).toBeChecked();
  });

  it("una celda vacía se puede confirmar como vacía", async () => {
    const corregir = vi.fn().mockResolvedValue(evaluacionDeNumeros());
    montar(corregir);
    await userEvent.click(within(filaDe(3)).getByRole("button", { name: "Confirmar fila 3" }));
    expect(corregir).toHaveBeenCalled();
    const cambio = corregir.mock.calls[0]![1];
    expect(cambio.filas).toEqual([{ item: 3 }]); // confirmada tal cual: sin respuesta, no se inventa un valor
  });

  it("los recortes de las celdas no abren la columna de observaciones", () => {
    const filas = evaluacionDeNumeros().filas;
    expect(hayObservaciones(plantillaDeNumeros(), filas)).toBe(false);
  });
});
