import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorApi } from "../api/cliente";
import type { PlantillaDef, ResumenPlantilla } from "../api/tipos";
import { estadoInicial, reducirEditor } from "../editor/historial";
import { EditorPlantilla } from "../pantallas/EditorPlantilla";
import { Plantillas, ultimasVersiones } from "../pantallas/Plantillas";
import { ContextoApi } from "../hooks";
import { render } from "./render";
import { clienteFalso } from "./datos";

function definicion(): PlantillaDef {
  const tabla = (item: number, texto: string, y: [number, number]) => ({
    seccion: "5.2 Denominativo",
    opciones: ["Sí", "No"],
    columnas_x: [
      [500, 530],
      [600, 630],
    ] as [number, number][],
    observacion_x: null,
    filas: [{ item, texto, y }],
  });
  return {
    esquema_version: 1,
    id: "sino",
    nombre: "Sí/No",
    version: 2,
    omr: { tinta_minima: 0.02, margen_relativo: 0.25 },
    paginas: [
      {
        imagen_referencia: "sino.png",
        tamano_px: [1000, 1400],
        cabecera: [{ campo: "paciente", caja: [100, 50, 400, 90], tipo: "texto" }],
        tablas: [tabla(1, "Martillo", [200, 230]), tabla(2, "Corbata", [260, 290])],
      },
    ],
  };
}

function montar(sobre: Parameters<typeof clienteFalso>[0] = {}) {
  const api = clienteFalso({ plantillaDef: vi.fn().mockResolvedValue(definicion()), ...sobre });
  render(
    <ContextoApi.Provider value={api}>
      <EditorPlantilla id="sino" />
    </ContextoApi.Provider>,
  );
  return api;
}

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("historial del editor", () => {
  it("deshacer y rehacer; escribir en el mismo campo es un solo paso", () => {
    const a = definicion();
    const b = { ...a, nombre: "B" };
    const c = { ...a, nombre: "Bc" };
    let s = estadoInicial(a);
    s = reducirEditor(s, { t: "aplicar", nuevo: b, clave: "nombre" });
    s = reducirEditor(s, { t: "aplicar", nuevo: c, clave: "nombre" });
    expect(s.pasado).toHaveLength(1);
    s = reducirEditor(s, { t: "deshacer" });
    expect(s.borrador.nombre).toBe("Sí/No");
    s = reducirEditor(s, { t: "rehacer" });
    expect(s.borrador.nombre).toBe("Bc");
  });

  it("un arrastre en vivo no ensucia el historial hasta que se cierra", () => {
    const a = definicion();
    let s = estadoInicial(a);
    s = reducirEditor(s, { t: "vivo", nuevo: { ...a, nombre: "mov" } });
    expect(s.pasado).toHaveLength(0);
    s = reducirEditor(s, { t: "cerrarArrastre", base: a });
    expect(s.pasado).toEqual([a]);
  });
});

describe("editor de plantillas", () => {
  it("muestra las preguntas por sección y no marca cambios al abrir", async () => {
    montar();
    expect(await screen.findByText(/2 preguntas/)).toBeInTheDocument();
    expect(screen.getByText("5.2 Denominativo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Guardar como versión 3/ })).toBeDisabled();
    expect(screen.queryByText("Cambios sin guardar")).not.toBeInTheDocument();
  });

  it("elegir una pregunta de la lista abre su panel y renombrarla marca el cambio", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /1\. Martillo/ }));
    const campo = screen.getByLabelText("Texto de la fila 1");
    await userEvent.clear(campo);
    await userEvent.type(campo, "Llave");
    expect(screen.getByText("Cambios sin guardar")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Guardar como versión 3/ })).toBeEnabled();
  });

  it("escribir un texto es un solo paso: un «Deshacer» lo vuelve al original", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /1\. Martillo/ }));
    await userEvent.type(screen.getByLabelText("Texto de la fila 1"), " grande");
    expect(screen.getByLabelText("Texto de la fila 1")).toHaveValue("Martillo grande");
    await userEvent.click(screen.getByRole("button", { name: "Deshacer" }));
    expect(screen.getByLabelText("Texto de la fila 1")).toHaveValue("Martillo");
  });

  it("agregar una pregunta y quitar otra; quitar la última fila quita la tabla", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Agregar pregunta Sí/No" }));
    expect(screen.getByText(/3 preguntas/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /1\. Martillo/ }));
    await userEvent.click(screen.getByRole("button", { name: "Quitar la fila 1" }));
    expect(screen.getByText(/2 preguntas/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /1\. Martillo/ })).not.toBeInTheDocument();
  });

  it("agregar y renombrar opciones", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /1\. Martillo/ }));
    await userEvent.click(screen.getByRole("button", { name: "Agregar opción" }));
    expect(screen.getByLabelText("Opción 3")).toHaveValue("Opción 3");
    expect(screen.getByTestId("celda-1-2")).toBeInTheDocument();
    const op = screen.getByLabelText("Opción 1");
    await userEvent.clear(op);
    await userEvent.type(op, "Correcto");
    expect(screen.getByLabelText("Opción 1")).toHaveValue("Correcto");
  });

  it("las flechas mueven la casilla elegida; con Mayús, de a 10", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /1\. Martillo/ }));
    expect(screen.getByTestId("celda-1-0")).toHaveAttribute("x", "500");
    const raiz = screen.getByRole("img", { name: /Hoja de la plantilla/ });
    fireEvent.keyDown(raiz, { key: "ArrowRight" });
    expect(screen.getByTestId("celda-1-0")).toHaveAttribute("x", "501");
    fireEvent.keyDown(raiz, { key: "ArrowRight", shiftKey: true });
    expect(screen.getByTestId("celda-1-0")).toHaveAttribute("x", "511");
  });

  it("los números de la caja se pueden escribir y respetan a la vecina", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /1\. Martillo/ }));
    fireEvent.change(screen.getByLabelText("Der."), { target: { value: "9999" } });
    expect(screen.getByTestId("celda-1-0")).toHaveAttribute("width", "100"); // tope: la columna siguiente (600)
  });

  it("guardar pide confirmación, manda la plantilla editada y avisa la versión", async () => {
    const guardarVersion = vi
      .fn()
      .mockResolvedValue({ id: "sino", nombre: "Sí/No", version: 3, paginas: 1, items: 2 });
    montar({ guardarVersion });
    const nombre = await screen.findByLabelText("Nombre de la plantilla");
    await userEvent.clear(nombre);
    await userEvent.type(nombre, "Corregida");
    await userEvent.click(screen.getByRole("button", { name: /Guardar como versión 3/ }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("versión 3");
    await userEvent.click(screen.getByRole("button", { name: "Sí, guardar" }));
    await waitFor(() => expect(guardarVersion).toHaveBeenCalled());
    expect(guardarVersion.mock.calls[0]![0]).toBe("sino");
    expect(guardarVersion.mock.calls[0]![1].nombre).toBe("Corregida");
    expect(await screen.findByRole("dialog")).toHaveTextContent("Quedó guardada como la versión 3");
  });

  it("si el servidor rechaza la plantilla lo dice en una ventana y no se pierde lo hecho", async () => {
    const guardarVersion = vi
      .fn()
      .mockRejectedValue(new ErrorApi(422, "plantilla_invalida", "Las filas se solapan."));
    montar({ guardarVersion });
    await userEvent.type(await screen.findByLabelText("Nombre de la plantilla"), "x");
    await userEvent.click(screen.getByRole("button", { name: /Guardar como versión 3/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Sí, guardar" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Las filas se solapan.");
    await userEvent.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(screen.getByLabelText("Nombre de la plantilla")).toHaveValue("Sí/Nox");
  });

  it("ofrece recuperar el borrador que quedó sin guardar", async () => {
    window.localStorage.setItem(
      "autoevalpsi.borrador.sino.2",
      JSON.stringify({ ...definicion(), nombre: "Recuperado" }),
    );
    montar();
    expect(await screen.findByRole("dialog")).toHaveTextContent("Cambios sin guardar");
    await userEvent.click(screen.getByRole("button", { name: "Sí, recuperarlos" }));
    expect(screen.getByLabelText("Nombre de la plantilla")).toHaveValue("Recuperado");
  });

  it("agrega un campo de la cabecera y no admite repetidos", async () => {
    montar();
    await userEvent.type(await screen.findByLabelText("Campo de la cabecera"), "cargo");
    await userEvent.click(screen.getByRole("button", { name: "Agregar" }));
    expect(screen.getByTestId("cabecera-cargo")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Campo de la cabecera"), "cargo");
    await userEvent.click(screen.getByRole("button", { name: "Agregar" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("no esté repetido");
  });
});

describe("pantalla de plantillas", () => {
  const r = (parcial: Partial<ResumenPlantilla>): ResumenPlantilla => ({
    id: "a",
    nombre: "A",
    version: 1,
    paginas: 1,
    items: 3,
    ...parcial,
  });

  it("muestra solo la última versión de cada plantilla", () => {
    const lista = [r({ version: 1 }), r({ version: 3 }), r({ id: "b", nombre: "B" })];
    expect(ultimasVersiones(lista).map((p) => [p.id, p.version])).toEqual([
      ["a", 3],
      ["b", 1],
    ]);
  });

  it("lista, ofrece editar y arma un borrador desde una foto", async () => {
    const plantillaDesdeFoto = vi
      .fn()
      .mockResolvedValue({ ...r({ id: "nuevo", nombre: "Nuevo", items: 61 }), secciones: 12 });
    const api = clienteFalso({
      plantillas: vi.fn().mockResolvedValue([r({ nombre: "Evaluación", version: 2 })]),
      plantillaDesdeFoto,
    });
    render(
      <ContextoApi.Provider value={api}>
        <Plantillas />
      </ContextoApi.Provider>,
    );
    expect(await screen.findByText(/Versión 2 · 3 preguntas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Editar" })).toHaveAttribute("href", "#/plantillas/a");
    expect(screen.getByRole("button", { name: "Armar el borrador" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Nombre del formulario"), "Nuevo");
    const foto = new File(["x"], "f.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByLabelText("Foto del formulario lleno"), foto);
    await userEvent.click(screen.getByRole("button", { name: "Armar el borrador" }));
    await waitFor(() => expect(plantillaDesdeFoto).toHaveBeenCalledWith(foto, "Nuevo"));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(/61 preguntas en 12 secciones/)).toBeInTheDocument();
  });
});
