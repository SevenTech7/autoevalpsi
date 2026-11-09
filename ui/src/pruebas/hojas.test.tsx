import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ErrorApi } from "../api/cliente";
import type { Cliente } from "../api/cliente";
import type { Plantilla } from "../api/tipos";
import { describirEstado } from "../componentes/TablaEvaluaciones";
import { ContextoApi } from "../hooks";
import { Plantillas } from "../pantallas/Plantillas";
import { PantallaRevision, Revision } from "../pantallas/Revision";
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
    const pestanas = screen.getByRole("tablist", { name: "Hojas de la evaluación" });
    expect(within(pestanas).getByRole("tab", { name: /Hoja 1/ })).toHaveAttribute("aria-selected", "true");
    expect(within(pestanas).getByRole("tab", { name: /Hoja 1/ })).toHaveTextContent("por revisar");
    const faltante = within(pestanas).getByRole("tab", { name: /Hoja 2/ });
    expect(faltante).toHaveTextContent("falta");
    await userEvent.click(faltante);
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(/Falta la foto de la hoja 2/)).toBeInTheDocument();
    expect(within(panel).getByText(/con el celular/)).toBeInTheDocument();
    const foto = new File(["x"], "h2.jpg", { type: "image/jpeg" });
    await userEvent.upload(within(panel).getByLabelText("Subir la foto de la hoja 2"), foto);
    await waitFor(() => expect(alSubirHoja).toHaveBeenCalledWith(1, foto));
  });

  it("al salir de la pantalla se deja de consultar la cola de la foto subida", async () => {
    const cola = vi.fn().mockResolvedValue({ trabajos: [{ id: "t1", estado: "leyendo" }] });
    const api = clienteFalso({
      evaluacion: vi.fn().mockResolvedValue(evaluacion({ cabecera_revisada: true })),
      plantilla: vi.fn().mockResolvedValue(dosHojas()),
      subirFoto: vi
        .fn()
        .mockResolvedValue({ trabajo: { id: "t1" }, repetir: false, problemas_calidad: [] }),
      cola,
    });
    const { unmount } = render(
      <ContextoApi.Provider value={api}>
        <PantallaRevision id="ev1" />
      </ContextoApi.Provider>,
    );
    await userEvent.click(await screen.findByRole("tab", { name: /Hoja 2/ }));
    const panel = screen.getByRole("tabpanel");
    await userEvent.upload(
      within(panel).getByLabelText("Subir la foto de la hoja 2"),
      new File(["x"], "h2.jpg", { type: "image/jpeg" }),
    );
    await waitFor(() => expect(cola).toHaveBeenCalledTimes(1));
    unmount();
    await new Promise((r) => setTimeout(r, 1800)); // más que el intervalo de sondeo (1,5 s)
    expect(cola).toHaveBeenCalledTimes(1);
  });

  it("con una sola hoja no aparecen las pestañas", () => {
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
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
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
