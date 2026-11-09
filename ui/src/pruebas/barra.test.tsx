import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Plantilla } from "../api/tipos";
import { Revision } from "../pantallas/Revision";
import { clienteFalso, evaluacion, fila, plantilla } from "./datos";
import { render } from "./render";

afterEach(() => vi.restoreAllMocks());

const resultado = { carpeta: "C:\Excel", evaluacion: "C:\Excel\a.xlsx", consolidado: "C:\Excel\c.xlsx" };

function dosHojasConFilas(): { ev: ReturnType<typeof evaluacion>; plantilla: Plantilla } {
  const p = plantilla();
  const dos: Plantilla = {
    ...p,
    paginas: [
      p.paginas[0]!,
      { ...p.paginas[0]!, tablas: [{ opciones: ["A"], filas: [{ item: 9, texto: "Pregunta de la segunda hoja" }] }] },
    ],
  };
  const ev = evaluacion({
    cabecera_revisada: true,
    filas: [
      fila({ item: 1 }),
      fila({ item: 2, revisada: true }),
      fila({ item: 3, revisada: true }),
      fila({ item: 9, pagina: 1, opcion: null, opcion_leida: null, revisada: false, banderas: ["sin_marca"] }),
    ],
    filas_pendientes: 1,
    paginas: [
      { ...evaluacion().paginas[0]! },
      { ...evaluacion().paginas[0]!, pagina: 1, foto_sha256: "b".repeat(64) },
    ],
  });
  return { ev, plantilla: dos };
}

function montar(ev = evaluacion({ cabecera_revisada: true, filas_pendientes: 0 }), extra = {}, p = plantilla()) {
  const props = {
    api: clienteFalso({ exportar: vi.fn().mockResolvedValue(resultado), evaluacion: vi.fn().mockResolvedValue(ev), ...extra }),
    evaluacion: ev,
    plantilla: p,
    alActualizar: vi.fn(),
    alDescartar: vi.fn(),
    alEliminar: vi.fn().mockResolvedValue(undefined),
  };
  render(<Revision {...props} />);
  return props;
}

describe("barra de la revisión", () => {
  it("el botón de exportar de arriba exporta igual que el del pie", async () => {
    const ev = evaluacion({ cabecera_revisada: true, filas_pendientes: 0, filas: [fila({ item: 1 }), fila({ item: 2 }), fila({ item: 3 })] });
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(ev, { exportar });
    const barra = screen.getAllByRole("button", { name: /^Exportar/ })[0]!;
    expect(barra.closest(".sticky")).not.toBeNull(); // está en la barra fija
    await userEvent.click(barra);
    await waitFor(() => expect(exportar).toHaveBeenCalledWith("ev1", false));
  });

  it("bloqueado dice por qué al pasar el cursor", () => {
    montar(evaluacion()); // faltan filas
    const barra = screen.getAllByRole("button", { name: /^Exportar/ })[0]!;
    expect(barra).toBeDisabled();
    expect(barra).toHaveAttribute("title", "Faltan 2 filas por revisar.");
  });

  it("muestra el avance de lo revisado", () => {
    montar(evaluacion()); // 1 de 3 revisada
    expect(screen.getByRole("progressbar", { name: "Filas revisadas" })).toHaveAttribute("aria-valuenow", "1");
    expect(screen.getByText("1 de 3 revisadas")).toBeInTheDocument();
  });

  it("eliminar y los atajos están en el menú «⋯»", async () => {
    const props = montar();
    expect(screen.queryByRole("button", { name: "Eliminar evaluación" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(screen.getByText(/Enter confirma/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Eliminar evaluación" }));
    await userEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Sí, eliminar" }));
    await waitFor(() => expect(props.alEliminar).toHaveBeenCalledTimes(1));
  });

  it("el menú se cierra con Esc", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: "Más acciones" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("pestañas por hoja", () => {
  it("cada pestaña muestra solo las filas de su hoja", async () => {
    const { ev, plantilla: p } = dosHojasConFilas();
    montar(ev, {}, p);
    const pestanas = screen.getByRole("tablist");
    // entra en la hoja que tiene algo por revisar (la 2)
    expect(within(pestanas).getByRole("tab", { name: /Hoja 2/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Pregunta de la segunda hoja")).toBeInTheDocument();
    expect(screen.queryByText("Puntualidad")).not.toBeInTheDocument();
    await userEvent.click(within(pestanas).getByRole("tab", { name: /Hoja 1/ }));
    expect(screen.getByText("Puntualidad")).toBeInTheDocument();
    expect(screen.queryByText("Pregunta de la segunda hoja")).not.toBeInTheDocument();
  });

  it("la pestaña dice si la hoja está lista o cuántas filas le faltan", () => {
    const { ev, plantilla: p } = dosHojasConFilas();
    montar(ev, {}, p);
    const pestanas = screen.getByRole("tablist");
    expect(within(pestanas).getByRole("tab", { name: /Hoja 1/ })).toHaveTextContent("✓");
    expect(within(pestanas).getByRole("tab", { name: /Hoja 2/ })).toHaveTextContent("1 por revisar");
  });
});
