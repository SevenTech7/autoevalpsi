import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { Cliente } from "../api/cliente";
import { ErrorApi } from "../api/cliente";
import { ContextoApi } from "../hooks";
import { Configuracion } from "../pantallas/Configuracion";
import { ListaEvaluaciones, filtrar } from "../pantallas/Evaluaciones";
import { TarjetaCelular, TarjetaPendientes, formatearRestante } from "../pantallas/Inicio";
import { clienteFalso, inicioVinculo, resumen } from "./datos";

function conApi(api: Cliente, hijo: ReactNode) {
  return render(<ContextoApi.Provider value={api}>{hijo}</ContextoApi.Provider>);
}

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as { pywebview?: unknown }).pywebview;
});

const LISTA = [
  resumen({ id: "a", paciente: "Ana Pérez", estado: "pendiente", filas_pendientes: 3 }),
  resumen({ id: "b", paciente: "Luis Díaz", estado: "revisada", filas_pendientes: 0 }),
  resumen({ id: "c", paciente: "Rosa Gil", estado: "exportada", filas_pendientes: 0 }),
  resumen({ id: "d", paciente: "", estado: "pendiente", filas_pendientes: 0 }),
];

describe("lista de evaluaciones", () => {
  it("muestra a cada paciente con su estado en palabras", () => {
    render(<ListaEvaluaciones evaluaciones={LISTA} />);
    expect(screen.getByRole("link", { name: "Ana Pérez" })).toHaveAttribute("href", "#/evaluaciones/a");
    expect(screen.getByText("Faltan 3 filas por revisar")).toBeInTheDocument();
    expect(screen.getByText("Lista para exportar")).toBeInTheDocument();
    expect(screen.getByText("Exportada")).toBeInTheDocument();
    expect(screen.getByText("Falta confirmar la cabecera")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sin nombre" })).toBeInTheDocument();
    expect(screen.getAllByText("07/11/2026").length).toBe(4);
  });

  it("los filtros dejan solo lo que corresponde y cuentan", async () => {
    render(<ListaEvaluaciones evaluaciones={LISTA} />);
    expect(screen.getByRole("button", { name: "Todas (4)" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Por revisar (2)" }));
    expect(screen.getByRole("link", { name: "Ana Pérez" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Luis Díaz" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Exportadas (1)" }));
    expect(screen.getByRole("link", { name: "Rosa Gil" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ana Pérez" })).not.toBeInTheDocument();
  });

  it("una lista vacía lo dice", () => {
    render(<ListaEvaluaciones evaluaciones={[]} />);
    expect(screen.getByText("No hay evaluaciones todavía.")).toBeInTheDocument();
  });

  it("filtrar no altera la lista original", () => {
    const copia = [...LISTA];
    expect(filtrar(LISTA, "listas").map((e) => e.id)).toEqual(["b"]);
    expect(LISTA).toEqual(copia);
  });
});

describe("pendientes en el inicio", () => {
  it("muestra solo lo no exportado y avisa cuántas fotos está leyendo", async () => {
    const api = clienteFalso({
      evaluaciones: vi.fn().mockResolvedValue(LISTA),
      cola: vi.fn().mockResolvedValue({ pendientes: 2, en_cola: 1, procesando: 1, lista: 0, error: 0 }),
    });
    conApi(api, <TarjetaPendientes />);
    expect(await screen.findByText("Ana Pérez")).toBeInTheDocument();
    expect(screen.queryByText("Rosa Gil")).not.toBeInTheDocument();
    expect(screen.getByText("Estoy leyendo 2 fotos…")).toBeInTheDocument();
  });

  it("si no hay nada pendiente lo dice, y si falla muestra el error", async () => {
    conApi(
      clienteFalso({
        evaluaciones: vi.fn().mockResolvedValue([LISTA[2]]),
        cola: vi.fn().mockResolvedValue({ pendientes: 0, en_cola: 0, procesando: 0, lista: 0, error: 0 }),
      }),
      <TarjetaPendientes />,
    );
    expect(await screen.findByText(/No hay nada pendiente/)).toBeInTheDocument();
  });

  it("un error del servidor se ve con su mensaje", async () => {
    conApi(
      clienteFalso({
        evaluaciones: vi.fn().mockRejectedValue(new ErrorApi(500, "x", "Se cayó la lectura.")),
        cola: vi.fn().mockResolvedValue({ pendientes: 0, en_cola: 0, procesando: 0, lista: 0, error: 0 }),
      }),
      <TarjetaPendientes />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Se cayó la lectura.");
  });
});

describe("vincular el celular", () => {
  it("formatea la cuenta regresiva", () => {
    expect(formatearRestante(300)).toBe("5:00");
    expect(formatearRestante(65)).toBe("1:05");
    expect(formatearRestante(0)).toBe("0:00");
  });

  it("muestra el QR, y al canjearlo el celular avisa que quedó vinculado", async () => {
    const vinculo = vi
      .fn()
      .mockResolvedValueOnce({ vinculado: false, creado: null, ultimo_uso: null }) // carga inicial
      .mockResolvedValueOnce({ vinculado: false, creado: null, ultimo_uso: null }) // al pulsar
      .mockResolvedValue({ vinculado: true, creado: "2026-11-07T10:00:00", ultimo_uso: null });
    const api = clienteFalso({ vinculo, iniciarVinculo: vi.fn().mockResolvedValue(inicioVinculo()) });
    conApi(api, <TarjetaCelular sondeoMs={20} />);

    await userEvent.click(await screen.findByRole("button", { name: "Vincular celular" }));
    const qr = await screen.findByAltText("Código QR para vincular el celular");
    expect(qr.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByText("5:00")).toBeInTheDocument();

    expect(await screen.findByText(/celular quedó vinculado/)).toBeInTheDocument();
    expect(screen.queryByAltText("Código QR para vincular el celular")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Desvincular" })).toBeInTheDocument();
  });

  it("reemplazar el celular: el vínculo viejo no cuenta como «ya vinculado»", async () => {
    const viejo = { vinculado: true, creado: "2026-11-01T08:00:00", ultimo_uso: null };
    const vinculo = vi.fn().mockResolvedValue(viejo);
    conApi(
      clienteFalso({ vinculo, iniciarVinculo: vi.fn().mockResolvedValue(inicioVinculo({ vinculado: true })) }),
      <TarjetaCelular sondeoMs={20} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Vincular otro celular" }));
    await screen.findByAltText("Código QR para vincular el celular");
    await new Promise((r) => setTimeout(r, 120)); // varios sondeos con el vínculo viejo
    expect(screen.getByAltText("Código QR para vincular el celular")).toBeInTheDocument();
    expect(screen.queryByText(/quedó vinculado/)).not.toBeInTheDocument();
  });

  it("sin red con IP privada explica qué hacer en vez de mostrar un QR", async () => {
    const api = clienteFalso({
      vinculo: vi.fn().mockResolvedValue({ vinculado: false, creado: null, ultimo_uso: null }),
      iniciarVinculo: vi
        .fn()
        .mockResolvedValue(inicioVinculo({ qr_svg: null, url: null, ip: null, ips: [], mensaje: "Conéctala al WiFi de la casa." })),
    });
    conApi(api, <TarjetaCelular />);
    await userEvent.click(await screen.findByRole("button", { name: "Vincular celular" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Conéctala al WiFi de la casa.");
    expect(screen.queryByAltText("Código QR para vincular el celular")).not.toBeInTheDocument();
  });

  it("con varias redes deja elegir otra IP y pide el código con ella", async () => {
    const iniciarVinculo = vi
      .fn()
      .mockResolvedValue(inicioVinculo({ ips: ["192.168.1.20", "10.0.0.5"], ip: "192.168.1.20" }));
    conApi(
      clienteFalso({
        vinculo: vi.fn().mockResolvedValue({ vinculado: false, creado: null, ultimo_uso: null }),
        iniciarVinculo,
      }),
      <TarjetaCelular sondeoMs={5000} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Vincular celular" }));
    await userEvent.selectOptions(await screen.findByLabelText("Red de la laptop"), "10.0.0.5");
    await waitFor(() => expect(iniciarVinculo).toHaveBeenLastCalledWith("10.0.0.5"));
  });

  it("desvincular pide confirmación", async () => {
    const desvincular = vi.fn().mockResolvedValue({ desvinculado: true });
    const vinculo = vi.fn().mockResolvedValue({ vinculado: true, creado: "x", ultimo_uso: null });
    conApi(clienteFalso({ vinculo, desvincular }), <TarjetaCelular />);
    const boton = await screen.findByRole("button", { name: "Desvincular" });

    vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await userEvent.click(boton);
    expect(desvincular).not.toHaveBeenCalled();

    vi.spyOn(window, "confirm").mockReturnValueOnce(true);
    await userEvent.click(boton);
    await waitFor(() => expect(desvincular).toHaveBeenCalledTimes(1));
  });
});

describe("configuración", () => {
  const config = { carpeta_exportacion: null, carpeta_exportacion_efectiva: "C:\\Datos\\exportaciones" };

  it("sin el puente del escritorio se escribe la ruta y se guarda", async () => {
    const guardar = vi
      .fn()
      .mockResolvedValue({ carpeta_exportacion: "D:\\Excel", carpeta_exportacion_efectiva: "D:\\Excel" });
    conApi(
      clienteFalso({ configuracion: vi.fn().mockResolvedValue(config), guardarCarpetaExportacion: guardar }),
      <Configuracion />,
    );
    expect(await screen.findByText("C:\\Datos\\exportaciones")).toBeInTheDocument();
    const guardarBtn = screen.getByRole("button", { name: "Guardar" });
    expect(guardarBtn).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Ruta de la carpeta"), "D:\\Excel");
    await userEvent.click(guardarBtn);
    await waitFor(() => expect(guardar).toHaveBeenCalledWith("D:\\Excel"));
    expect(await screen.findByText(/la carpeta quedó guardada/)).toBeInTheDocument();
  });

  it("el error del servidor sobre la carpeta se muestra tal cual", async () => {
    conApi(
      clienteFalso({
        configuracion: vi.fn().mockResolvedValue(config),
        guardarCarpetaExportacion: vi.fn().mockRejectedValue(new ErrorApi(422, "carpeta_invalida", "No se pudo usar la carpeta.")),
      }),
      <Configuracion />,
    );
    await userEvent.type(await screen.findByLabelText("Ruta de la carpeta"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo usar la carpeta.");
  });

  it("con el puente del escritorio usa el diálogo nativo y recarga; cancelar no hace nada", async () => {
    const elegir = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce("E:\\Mis Excel");
    (window as unknown as { pywebview: unknown }).pywebview = { api: { elegir_carpeta_exportacion: elegir } };
    const configuracion = vi
      .fn()
      .mockResolvedValueOnce(config)
      .mockResolvedValue({ carpeta_exportacion: "E:\\Mis Excel", carpeta_exportacion_efectiva: "E:\\Mis Excel" });
    conApi(clienteFalso({ configuracion }), <Configuracion />);

    const boton = await screen.findByRole("button", { name: /Elegir otra carpeta/ });
    expect(screen.queryByLabelText("Ruta de la carpeta")).not.toBeInTheDocument();
    await userEvent.click(boton);
    expect(configuracion).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/quedó guardada/)).not.toBeInTheDocument();

    await userEvent.click(boton);
    expect(await screen.findByText("E:\\Mis Excel")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Volver a la carpeta por defecto" })).toBeInTheDocument();
  });

  it("borrar fotos solo toca lo exportado y pide confirmación", async () => {
    const borrarFotos = vi.fn().mockResolvedValue({ borrados: 2 });
    const api = clienteFalso({
      configuracion: vi.fn().mockResolvedValue(config),
      evaluaciones: vi.fn().mockResolvedValue(LISTA),
      borrarFotos,
    });
    conApi(api, <Configuracion />);
    const boton = await screen.findByRole("button", { name: /Borrar las fotos/ });

    vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await userEvent.click(boton);
    expect(borrarFotos).not.toHaveBeenCalled();

    vi.spyOn(window, "confirm").mockReturnValueOnce(true);
    await userEvent.click(boton);
    expect(await screen.findByText(/se borraron 2 foto\(s\) de 1 evaluación/)).toBeInTheDocument();
    expect(borrarFotos).toHaveBeenCalledTimes(1);
    expect(borrarFotos).toHaveBeenCalledWith("c");
  });

  it("borrar fotos sin nada exportado lo explica", async () => {
    const api = clienteFalso({
      configuracion: vi.fn().mockResolvedValue(config),
      evaluaciones: vi.fn().mockResolvedValue([LISTA[0]]),
    });
    conApi(api, <Configuracion />);
    await userEvent.click(await screen.findByRole("button", { name: /Borrar las fotos/ }));
    expect(await screen.findByText("Todavía no hay evaluaciones exportadas.")).toBeInTheDocument();
  });
});

describe("la aplicación", () => {
  it("sin token explica que hay que abrirla desde AutoEvalPsi", () => {
    render(<App token={null} />);
    const aviso = screen.getByRole("alert");
    expect(within(aviso).getByText(/debe abrirse desde la aplicación/)).toBeInTheDocument();
  });

  it("el menú marca la pantalla actual", () => {
    window.location.hash = "#/configuracion";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ carpeta_exportacion: null, carpeta_exportacion_efectiva: "C:\\x" })),
      ),
    );
    render(<App token="abc" />);
    expect(screen.getByRole("link", { name: "Configuración" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Inicio" })).not.toHaveAttribute("aria-current");
    vi.unstubAllGlobals();
    window.location.hash = "";
  });
});
