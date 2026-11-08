import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorApi } from "../api/cliente";
import type { Cliente } from "../api/cliente";
import type { Plantilla } from "../api/tipos";
import { describirEstado } from "../componentes/TablaEvaluaciones";
import { ContextoApi } from "../hooks";
import { Plantillas } from "../pantallas/Plantillas";
import { Revision } from "../pantallas/Revision";
import { clienteFalso, evaluacion, plantilla, resumen } from "./datos";
import { render } from "./render";

afterEach(() => vi.restoreAllMocks());

function dosHojas(): Plantilla {
  const p = plantilla();
  return { ...p, paginas: [p.paginas[0]!, { ...p.paginas[0]!, tablas: [{ opciones: ["A"], filas: [{ item: 9, texto: "Otra" }] }] }] };
}

describe("hojas de una evaluación", () => {
  it("la lista dice que faltan hojas por subir", () => {
    expect(describirEstado(resumen({ paginas_total: 2, paginas_subidas: 1 }))).toBe(
      "Faltan hojas por subir (1 de 2)",
    );
    expect(describirEstado(resumen({ paginas_total: 2, paginas_subidas: 2, filas_pendientes: 3 }))).toMatch(
      /Faltan 3 filas/,
    );
  });

  it("la revisión muestra qué hoja falta y deja subirla desde la laptop", async () => {
    const alSubirHoja = vi.fn().mockResolvedValue(undefined);
    render(
      <Revision
        api={clienteFalso()}
        evaluacion={evaluacion({ cabecera_revisada: true })}
        plantilla={dosHojas()}
        alActualizar={vi.fn()}
        alDescartar={vi.fn()}
        alSubirHoja={alSubirHoja}
      />,
    );
    const panel = screen.getByRole("region", { name: "Hojas de la evaluación" });
    expect(within(panel).getByText("Hojas de esta evaluación (1 de 2)")).toBeInTheDocument();
    expect(within(panel).getByText("✓ Ya está subida")).toBeInTheDocument();
    expect(within(panel).getByText(/con el celular/)).toBeInTheDocument();
    const foto = new File(["x"], "h2.jpg", { type: "image/jpeg" });
    await userEvent.upload(within(panel).getByLabelText("Subir la foto de la hoja 2"), foto);
    await waitFor(() => expect(alSubirHoja).toHaveBeenCalledWith(1, foto));
  });

  it("con una sola hoja no aparece el panel", () => {
    render(
      <Revision
        api={clienteFalso()}
        evaluacion={evaluacion({ cabecera_revisada: true })}
        plantilla={plantilla()}
        alActualizar={vi.fn()}
        alDescartar={vi.fn()}
        alSubirHoja={vi.fn()}
      />,
    );
    expect(screen.queryByRole("region", { name: "Hojas de la evaluación" })).not.toBeInTheDocument();
  });
});

describe("eliminar un formulario", () => {
  const lista = [{ id: "demo", nombre: "Demo", version: 1, paginas: 1, items: 3 }];

  function montar(eliminarPlantilla: Cliente["eliminarPlantilla"]) {
    const api = clienteFalso({ plantillas: vi.fn().mockResolvedValue(lista), eliminarPlantilla });
    render(
      <ContextoApi.Provider value={api}>
        <Plantillas />
      </ContextoApi.Provider>,
    );
  }

  it("sin evaluaciones basta una confirmación", async () => {
    const eliminarPlantilla = vi.fn().mockResolvedValue({ eliminada: true, evaluaciones_eliminadas: 0 });
    montar(eliminarPlantilla);
    await userEvent.click(await screen.findByRole("button", { name: "Eliminar el formulario Demo" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Sí, eliminar" }));
    await waitFor(() => expect(eliminarPlantilla).toHaveBeenCalledWith("demo"));
  });

  it("con evaluaciones lo dice y pide confirmar de nuevo", async () => {
    const eliminarPlantilla = vi
      .fn()
      .mockRejectedValueOnce(new ErrorApi(409, "plantilla_en_uso", "Hay 2 evaluaciones hechas con este formulario."))
      .mockResolvedValue({ eliminada: true, evaluaciones_eliminadas: 2 });
    montar(eliminarPlantilla);
    await userEvent.click(await screen.findByRole("button", { name: "Eliminar el formulario Demo" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Sí, eliminar" }));
    const segunda = await screen.findByRole("dialog");
    expect(segunda).toHaveTextContent("Hay 2 evaluaciones");
    await userEvent.click(within(segunda).getByRole("button", { name: "Sí, eliminar todo" }));
    await waitFor(() => expect(eliminarPlantilla).toHaveBeenLastCalledWith("demo", true));
  });
});
