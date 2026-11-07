import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Cliente } from "../api/cliente";
import { ErrorApi } from "../api/cliente";
import type { Evaluacion } from "../api/tipos";
import { Exportar, motivoBloqueo } from "../componentes/Exportar";
import { Revision } from "../pantallas/Revision";
import { render } from "./render";
import { clienteFalso, evaluacion, fila, plantilla } from "./datos";

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as { pywebview?: unknown }).pywebview;
});

const lista = (parcial: Partial<Evaluacion> = {}) =>
  evaluacion({
    cabecera_revisada: true,
    filas: [fila({ item: 1 }), fila({ item: 2 }), fila({ item: 3 })],
    filas_pendientes: 0,
    ...parcial,
  });

const resultado = {
  carpeta: "C:\\Excel",
  evaluacion: "C:\\Excel\\Ana_Perez_2026-11-07.xlsx",
  consolidado: "C:\\Excel\\consolidado.xlsx",
};

function montar(api: Cliente, ev = lista(), cambiosSinGuardar = false) {
  const alExportar = vi.fn();
  render(<Exportar api={api} evaluacion={ev} cambiosSinGuardar={cambiosSinGuardar} alExportar={alExportar} />);
  return { alExportar };
}

const boton = () => screen.getByRole("button", { name: /Exportar/ });

function ventanaDeEscritorio(api: Record<string, unknown>) {
  (window as unknown as { pywebview: unknown }).pywebview = { api };
}

describe("motivoBloqueo", () => {
  it("dice qué falta, en orden", () => {
    expect(motivoBloqueo(evaluacion(), false)).toBe("Faltan 2 filas por revisar.");
    expect(motivoBloqueo(evaluacion({ filas_pendientes: 1 }), false)).toBe("Falta revisar 1 fila.");
    expect(motivoBloqueo(lista({ cabecera_revisada: false }), false)).toBe("Falta confirmar los datos de la hoja.");
    expect(motivoBloqueo(lista(), true)).toMatch(/cambios sin confirmar/);
    expect(motivoBloqueo(lista(), false)).toBeNull();
  });
});

describe("botón de exportar", () => {
  it("está deshabilitado mientras falta algo y lo explica", () => {
    montar(clienteFalso(), evaluacion());
    expect(boton()).toBeDisabled();
    expect(screen.getByText(/Faltan 2 filas por revisar\./)).toBeInTheDocument();
  });

  it("está deshabilitado con cambios sin confirmar aunque todo esté revisado", () => {
    montar(clienteFalso(), lista(), true);
    expect(boton()).toBeDisabled();
  });

  it("con todo revisado exporta, avisa dónde quedó y refresca la evaluación", async () => {
    const exportar = vi.fn().mockResolvedValue(resultado);
    const exportada = lista({ estado: "exportada" });
    const api = clienteFalso({ exportar, evaluacion: vi.fn().mockResolvedValue(exportada) });
    const { alExportar } = montar(api);
    expect(boton()).toBeEnabled();
    await userEvent.click(boton());
    const popup = await screen.findByRole("dialog");
    expect(alExportar).toHaveBeenCalledWith(exportada);
    expect(exportar).toHaveBeenCalledWith("ev1", false);
    expect(popup).toHaveTextContent("Excel exportado");
    expect(popup).toHaveTextContent("Ana_Perez_2026-11-07.xlsx");
    expect(popup).toHaveTextContent("C:\\Excel");
    expect(screen.queryByRole("button", { name: "Abrir la carpeta" })).not.toBeInTheDocument(); // sin ventana
    await userEvent.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("las iniciales se piden con la casilla", async () => {
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(clienteFalso({ exportar, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(screen.getByLabelText(/solo las iniciales/));
    await userEvent.click(boton());
    await waitFor(() => expect(exportar).toHaveBeenCalledWith("ev1", true));
  });

  it("una evaluación ya exportada se puede exportar de nuevo", () => {
    montar(clienteFalso(), lista({ estado: "exportada" }));
    expect(screen.getByText(/ya se exportó/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar de nuevo" })).toBeEnabled();
  });
});

describe("archivo abierto y otros errores", () => {
  it("si el Excel está abierto lo dice en una ventana con el mensaje del servidor y deja reintentar", async () => {
    const exportar = vi
      .fn()
      .mockRejectedValueOnce(
        new ErrorApi(409, "archivo_bloqueado", "No se pudo guardar «consolidado.xlsx». Si está abierto en Excel, ciérralo."),
      )
      .mockResolvedValueOnce(resultado);
    const { alExportar } = montar(clienteFalso({ exportar, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(boton());
    const popup = await screen.findByRole("alertdialog");
    expect(popup).toHaveTextContent("Si está abierto en Excel, ciérralo.");
    expect(alExportar).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(boton()).toBeEnabled();
    await userEvent.click(boton());
    await waitFor(() => expect(alExportar).toHaveBeenCalled());
    expect(await screen.findByRole("dialog")).toHaveTextContent("Excel exportado");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});

describe("carpeta y ventana de escritorio", () => {
  it("la primera vez pide la carpeta con el diálogo y luego exporta", async () => {
    const elegir = vi.fn().mockResolvedValue("C:\\Excel");
    ventanaDeEscritorio({ elegir_carpeta_exportacion: elegir });
    const exportar = vi.fn().mockResolvedValue(resultado);
    const configuracion = vi.fn().mockResolvedValue({ carpeta_exportacion: null, carpeta_exportacion_efectiva: "x" });
    montar(clienteFalso({ exportar, configuracion, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(boton());
    await screen.findByRole("dialog");
    expect(exportar).toHaveBeenCalled();
    expect(elegir).toHaveBeenCalledTimes(1);
  });

  it("si cancela el diálogo no exporta y se lo dice", async () => {
    ventanaDeEscritorio({ elegir_carpeta_exportacion: vi.fn().mockResolvedValue(null) });
    const exportar = vi.fn();
    const configuracion = vi.fn().mockResolvedValue({ carpeta_exportacion: null, carpeta_exportacion_efectiva: "x" });
    montar(clienteFalso({ exportar, configuracion }));
    await userEvent.click(boton());
    expect(await screen.findByRole("dialog")).toHaveTextContent("No se exportó: elige la carpeta");
    expect(exportar).not.toHaveBeenCalled();
  });

  it("con la carpeta ya elegida no la vuelve a pedir, y al terminar ofrece abrirla", async () => {
    const elegir = vi.fn();
    const abrir = vi.fn().mockResolvedValue(true);
    ventanaDeEscritorio({ elegir_carpeta_exportacion: elegir, abrir_carpeta: abrir });
    const configuracion = vi
      .fn()
      .mockResolvedValue({ carpeta_exportacion: "C:\\Excel", carpeta_exportacion_efectiva: "C:\\Excel" });
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(clienteFalso({ exportar, configuracion, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(boton());
    await userEvent.click(await screen.findByRole("button", { name: "Abrir la carpeta" }));
    expect(elegir).not.toHaveBeenCalled();
    expect(abrir).toHaveBeenCalledWith("C:\\Excel");
  });
});

describe("borrar las fotos (AP-D1)", () => {
  it("no se borra nada por defecto", async () => {
    const borrarFotos = vi.fn();
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(clienteFalso({ exportar, borrarFotos, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(boton());
    await screen.findByRole("dialog");
    expect(exportar).toHaveBeenCalled();
    expect(borrarFotos).not.toHaveBeenCalled();
  });

  it("con la casilla y la confirmación en la ventana borra las fotos después de exportar", async () => {
    const borrarFotos = vi.fn().mockResolvedValue({ borrados: 1 });
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(clienteFalso({ exportar, borrarFotos, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(screen.getByLabelText(/Borrar las fotos de esta evaluación/));
    await userEvent.click(boton());
    expect(await screen.findByRole("dialog")).toHaveTextContent("se borrarán las fotos");
    await userEvent.click(screen.getByRole("button", { name: "Sí, exportar y borrar" }));
    await waitFor(() => expect(borrarFotos).toHaveBeenCalledWith("ev1"));
    expect(exportar).toHaveBeenCalled();
  });

  it("si cancela la ventana, no exporta ni borra", async () => {
    const exportar = vi.fn();
    montar(clienteFalso({ exportar }));
    await userEvent.click(screen.getByLabelText(/Borrar las fotos de esta evaluación/));
    await userEvent.click(boton());
    await userEvent.click(await screen.findByRole("button", { name: "Cancelar" }));
    expect(exportar).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("si el Excel sale pero las fotos no se borran, la ventana lo dice", async () => {
    const borrarFotos = vi.fn().mockRejectedValue(new ErrorApi(500, "x", "Sin permiso."));
    const exportar = vi.fn().mockResolvedValue(resultado);
    montar(clienteFalso({ exportar, borrarFotos, evaluacion: vi.fn().mockResolvedValue(lista()) }));
    await userEvent.click(screen.getByLabelText(/Borrar las fotos de esta evaluación/));
    await userEvent.click(boton());
    await userEvent.click(await screen.findByRole("button", { name: "Sí, exportar y borrar" }));
    const popup = await screen.findByRole("dialog");
    expect(popup).toHaveTextContent("Excel exportado");
    expect(popup).toHaveTextContent("Las fotos no se pudieron borrar: Sin permiso.");
  });
});

describe("dentro de la pantalla de revisión", () => {
  it("la cabecera editada sin confirmar bloquea la exportación", async () => {
    render(
      <Revision
        api={clienteFalso()}
        evaluacion={lista()}
        plantilla={plantilla()}
        alActualizar={vi.fn()}
        alDescartar={vi.fn()}
      />,
    );
    expect(boton()).toBeEnabled();
    await userEvent.type(screen.getByLabelText("Paciente"), "x");
    expect(boton()).toBeDisabled();
    expect(screen.getByText(/cambios sin confirmar/)).toBeInTheDocument();
  });
});
