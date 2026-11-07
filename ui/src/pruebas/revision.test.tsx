import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Cliente } from "../api/cliente";
import { ErrorApi } from "../api/cliente";
import type { Evaluacion } from "../api/tipos";
import { ContextoApi } from "../hooks";
import { PantallaRevision, Revision, describirBandera, textoFaltan } from "../pantallas/Revision";
import { clienteFalso, evaluacion, fila, plantilla } from "./datos";

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
});

/** Respuesta del servidor tras confirmar los ítems dados. */
function confirmada(ev: Evaluacion, ...items: number[]): Evaluacion {
  const filas = ev.filas.map((f) => (items.includes(f.item) ? { ...f, revisada: true } : f));
  return { ...ev, filas, filas_pendientes: filas.filter((f) => !f.revisada).length };
}

function montar(api: Cliente, ev = evaluacion()) {
  const alActualizar = vi.fn();
  const alDescartar = vi.fn().mockResolvedValue(undefined);
  render(
    <Revision
      api={api}
      evaluacion={ev}
      plantilla={plantilla()}
      alActualizar={alActualizar}
      alDescartar={alDescartar}
    />,
  );
  return { alActualizar, alDescartar };
}

const filaDe = (item: number) => document.querySelector<HTMLElement>(`[data-item="${item}"]`)!;

describe("textos", () => {
  it("cuenta lo que falta en palabras", () => {
    expect(textoFaltan(0)).toBe("Todas las filas están revisadas");
    expect(textoFaltan(1)).toBe("Falta revisar 1 fila");
    expect(textoFaltan(4)).toBe("Faltan 4 filas por revisar");
  });

  it("traduce las banderas y deja pasar las desconocidas", () => {
    expect(describirBandera("doble_marca")).toBe("Hay más de una marca");
    expect(describirBandera("algo_nuevo")).toBe("algo_nuevo");
  });
});

describe("pantalla de revisión", () => {
  it("muestra lo que falta, los ítems con su texto y las banderas en palabras", () => {
    montar(clienteFalso());
    expect(screen.getByText("Faltan 2 filas por revisar")).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /Trato con el equipo/ })).toBeInTheDocument();
    expect(within(filaDe(2)).getByText("Hay más de una marca")).toBeInTheDocument();
    expect(within(filaDe(2)).getByText("El texto leído es dudoso")).toBeInTheDocument();
    expect(within(filaDe(3)).getByText("No se ve ninguna marca")).toBeInTheDocument();
    expect(within(filaDe(1)).getByText("Revisada")).toBeInTheDocument();
    expect(within(filaDe(2)).getByText("Por revisar")).toBeInTheDocument();
  });

  it("empieza en la primera fila por revisar y enseña el recorte con el token en la URL", () => {
    montar(clienteFalso());
    expect(filaDe(2)).toHaveAttribute("aria-current", "true");
    expect(filaDe(1)).not.toHaveAttribute("aria-current");
    const img = screen.getByAltText("Observación escrita a mano del ítem 2");
    expect(img).toHaveAttribute("src", "/recorte/ev1/2");
    expect(within(filaDe(1)).queryByAltText(/Observación escrita a mano/)).not.toBeInTheDocument();
  });

  it("el texto del OCR es siempre una sugerencia: se avisa y se puede editar", async () => {
    montar(clienteFalso());
    const caja = screen.getByLabelText(/Observación del ítem 2/);
    expect(caja).toHaveValue("llega tarde");
    expect(screen.getByText(/leída de la foto: puede tener errores/)).toBeInTheDocument();
    await userEvent.clear(caja);
    await userEvent.type(caja, "llegó tarde dos veces");
    expect(screen.queryByText(/leída de la foto/)).not.toBeInTheDocument();
    expect(within(filaDe(2)).getByText("Con cambios")).toBeInTheDocument();
  });

  it("clic en una casilla cambia la respuesta y «Confirmar» manda solo lo cambiado", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue(confirmada(ev, 2));
    const { alActualizar } = montar(clienteFalso({ corregirEvaluacion: corregir }), ev);

    await userEvent.click(within(filaDe(2)).getByRole("radio", { name: /B/ }));
    expect(within(filaDe(2)).getByRole("radio", { name: /B/ })).toBeChecked();
    await userEvent.click(within(filaDe(2)).getByRole("button", { name: "Confirmar fila 2" }));

    await waitFor(() => expect(alActualizar).toHaveBeenCalledTimes(1));
    expect(corregir).toHaveBeenCalledWith("ev1", { filas: [{ item: 2, opcion: "B" }] });
    expect(alActualizar).toHaveBeenCalledWith(expect.objectContaining({ filas_pendientes: 1 }));
  });

  it("«Sin respuesta» se manda como null explícito", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue(confirmada(ev, 3));
    montar(clienteFalso({ corregirEvaluacion: corregir }), ev);
    await userEvent.click(within(filaDe(3)).getByRole("radio", { name: /Sin respuesta/ }));
    await userEvent.click(within(filaDe(3)).getByRole("button", { name: "Confirmar fila 3" }));
    await waitFor(() => expect(corregir).toHaveBeenCalled());
    expect(corregir).toHaveBeenCalledWith("ev1", { filas: [{ item: 3, opcion: null }] });
  });

  it("confirmar sin tocar nada manda solo el ítem (es la confirmación de la persona)", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue(confirmada(ev, 2));
    montar(clienteFalso({ corregirEvaluacion: corregir }), ev);
    await userEvent.click(within(filaDe(2)).getByRole("button", { name: "Confirmar fila 2" }));
    await waitFor(() => expect(corregir).toHaveBeenCalled());
    expect(corregir).toHaveBeenCalledWith("ev1", { filas: [{ item: 2 }] });
  });

  it("una fila ya revisada y sin cambios no se vuelve a confirmar", () => {
    montar(clienteFalso());
    expect(within(filaDe(1)).getByRole("button", { name: "Confirmar fila 1" })).toBeDisabled();
  });

  it("si el servidor rechaza, se ve el mensaje y no se pierde lo escrito", async () => {
    const corregir = vi.fn().mockRejectedValue(new ErrorApi(422, "opcion_invalida", "Esa opción no es válida."));
    const { alActualizar } = montar(clienteFalso({ corregirEvaluacion: corregir }));
    await userEvent.click(within(filaDe(2)).getByRole("radio", { name: /C/ }));
    await userEvent.click(within(filaDe(2)).getByRole("button", { name: "Confirmar fila 2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Esa opción no es válida.");
    expect(alActualizar).not.toHaveBeenCalled();
    expect(within(filaDe(2)).getByRole("radio", { name: /C/ })).toBeChecked();
  });
});

describe("teclado", () => {
  it("↑/↓ cambian de fila, un número elige la opción y Enter confirma y pasa a la siguiente por revisar", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue(confirmada(ev, 2));
    montar(clienteFalso({ corregirEvaluacion: corregir }), ev);
    const user = userEvent.setup();

    expect(filaDe(2)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowUp}");
    expect(filaDe(1)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowUp}"); // no pasa del principio
    expect(filaDe(1)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}"); // ni del final
    expect(filaDe(3)).toHaveAttribute("aria-current", "true");
    await user.keyboard("{ArrowUp}");
    expect(filaDe(2)).toHaveAttribute("aria-current", "true");

    await user.keyboard("2");
    expect(within(filaDe(2)).getByRole("radio", { name: /B/ })).toBeChecked();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(corregir).toHaveBeenCalledWith("ev1", { filas: [{ item: 2, opcion: "B" }] }));
    await waitFor(() => expect(filaDe(3)).toHaveAttribute("aria-current", "true"));
  });

  it("un número que no es una opción no hace nada, y 0 es «sin respuesta»", async () => {
    montar(clienteFalso());
    const user = userEvent.setup();
    await user.keyboard("9");
    expect(within(filaDe(2)).getByRole("radio", { name: /Sin respuesta/ })).toBeChecked(); // lo leído: ninguna
    await user.keyboard("1");
    expect(within(filaDe(2)).getByRole("radio", { name: /A/ })).toBeChecked();
    await user.keyboard("0");
    expect(within(filaDe(2)).getByRole("radio", { name: /Sin respuesta/ })).toBeChecked();
  });

  it("escribiendo en una observación las teclas no cambian la respuesta; Ctrl+Enter confirma", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue(confirmada(ev, 2));
    montar(clienteFalso({ corregirEvaluacion: corregir }), ev);
    const caja = screen.getByLabelText(/Observación del ítem 2/);
    await userEvent.clear(caja);
    await userEvent.type(caja, "12 veces");
    expect(within(filaDe(2)).getByRole("radio", { name: /Sin respuesta/ })).toBeChecked(); // sigue igual
    expect(corregir).not.toHaveBeenCalled();

    fireEvent.keyDown(caja, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(corregir).toHaveBeenCalledTimes(1));
    expect(corregir).toHaveBeenCalledWith("ev1", { filas: [{ item: 2, observacion: "12 veces" }] });
  });
});

describe("tabla compacta", () => {
  it("una columna por opción y los avisos como iconos con su motivo al pasar el ratón", () => {
    montar(clienteFalso());
    for (const o of ["A", "B", "C"]) expect(screen.getByRole("columnheader", { name: o })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Avisos" })).toBeInTheDocument();
    const avisos = within(filaDe(2)).getAllByRole("tooltip");
    expect(avisos.map((a) => a.textContent)).toEqual(["Hay más de una marca", "El texto leído es dudoso"]);
    expect(within(filaDe(1)).queryAllByRole("tooltip")).toHaveLength(0);
  });

  it("filas seguidas con las mismas opciones comparten una sola tabla", () => {
    montar(clienteFalso());
    expect(document.querySelectorAll("table")).toHaveLength(1);
  });

  it("sin columna de observación si la hoja no la tiene ni hay nada leído", () => {
    const ev = evaluacion({
      filas: [fila({ item: 1 }), fila({ item: 2 }), fila({ item: 3 })],
      filas_pendientes: 0,
    });
    montar(clienteFalso(), ev);
    expect(screen.queryByRole("columnheader", { name: "Observación" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Observación del ítem/)).not.toBeInTheDocument();
  });

  it("si la foto no calzó con el formulario lo dice una vez para toda la hoja", () => {
    const ev = evaluacion();
    ev.paginas[0]!.registro = { ok: false };
    montar(clienteFalso(), ev);
    expect(screen.getByRole("alert")).toHaveTextContent("La foto no calzó bien con el formulario");
  });
});

describe("filtro, cabecera y fotos", () => {
  it("«Mostrar solo lo que falta» oculta lo ya revisado", async () => {
    montar(clienteFalso());
    expect(screen.getByRole("rowheader", { name: /Puntualidad/ })).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Mostrar solo lo que falta"));
    expect(screen.queryByRole("rowheader", { name: /Puntualidad/ })).not.toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /Trato con el equipo/ })).toBeInTheDocument();
  });

  it("con todo revisado lo dice, y queda lista para exportar si la cabecera está confirmada", () => {
    const ev = evaluacion({
      cabecera_revisada: true,
      filas: [fila({ item: 1 }), fila({ item: 2 }), fila({ item: 3 })],
      filas_pendientes: 0,
    });
    montar(clienteFalso(), ev);
    expect(screen.getByText("Todas las filas están revisadas · Lista para exportar")).toBeInTheDocument();
  });

  it("confirmar la cabecera manda paciente y campos, con el recorte a la vista", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue({ ...ev, cabecera_revisada: true, paciente: "Ana Pérez G." });
    montar(clienteFalso({ corregirEvaluacion: corregir }), ev);
    expect(screen.getByAltText("Lo escrito en «Paciente»")).toHaveAttribute("src", "/cabecera/ev1/paciente");
    expect(screen.getByText("Sin confirmar")).toBeInTheDocument();

    const paciente = screen.getByLabelText("Paciente");
    await userEvent.clear(paciente);
    await userEvent.type(paciente, "Ana Pérez G.");
    await userEvent.click(screen.getByRole("button", { name: "Confirmar datos de la hoja" }));
    await waitFor(() => expect(corregir).toHaveBeenCalled());
    expect(corregir).toHaveBeenCalledWith("ev1", { paciente: "Ana Pérez G.", cabecera: { fecha: "5/11" } });
  });

  it("descartar una foto pide confirmación y avisa a quien la descarta", async () => {
    const { alDescartar } = montar(clienteFalso());
    const boton = screen.getByRole("button", { name: "Descartar esta foto" });
    vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await userEvent.click(boton);
    expect(alDescartar).not.toHaveBeenCalled();
    vi.spyOn(window, "confirm").mockReturnValueOnce(true);
    await userEvent.click(boton);
    expect(alDescartar).toHaveBeenCalledWith(0);
  });

  it("muestra los avisos de calidad de la hoja", () => {
    const ev = evaluacion();
    ev.paginas[0]!.problemas_calidad = ["La foto está desenfocada."];
    montar(clienteFalso(), ev);
    expect(screen.getByText(/La foto está desenfocada\./)).toBeInTheDocument();
  });
});

describe("PantallaRevision", () => {
  function pantalla(api: Cliente, id = "ev1") {
    return render(
      <ContextoApi.Provider value={api}>
        <PantallaRevision id={id} />
      </ContextoApi.Provider>,
    );
  }

  it("carga la evaluación con su plantilla y la muestra", async () => {
    const api = clienteFalso({
      evaluacion: vi.fn().mockResolvedValue(evaluacion()),
      plantilla: vi.fn().mockResolvedValue(plantilla()),
    });
    pantalla(api);
    expect(await screen.findByRole("rowheader", { name: /Trato con el equipo/ })).toBeInTheDocument();
    expect(api.plantilla).toHaveBeenCalledWith("evaluacion-continua", 1);
  });

  it("si no se puede cargar, lo dice con el mensaje del servidor", async () => {
    const api = clienteFalso({
      evaluacion: vi.fn().mockRejectedValue(new ErrorApi(404, "evaluacion_inexistente", "No existe esa evaluación.")),
    });
    pantalla(api, "nada");
    expect(await screen.findByRole("alert")).toHaveTextContent("No existe esa evaluación.");
  });

  it("descartar una de varias fotos recarga; descartar la única vuelve a la lista", async () => {
    const descartarPagina = vi
      .fn()
      .mockResolvedValueOnce({ evaluacion_eliminada: false })
      .mockResolvedValueOnce({ evaluacion_eliminada: true });
    const api = clienteFalso({
      evaluacion: vi.fn().mockResolvedValue(evaluacion()),
      plantilla: vi.fn().mockResolvedValue(plantilla()),
      descartarPagina,
    });
    pantalla(api);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    await userEvent.click(await screen.findByRole("button", { name: "Descartar esta foto" }));
    await waitFor(() => expect(api.evaluacion).toHaveBeenCalledTimes(2)); // recargó
    expect(window.location.hash).toBe("");

    await userEvent.click(screen.getByRole("button", { name: "Descartar esta foto" }));
    await waitFor(() => expect(window.location.hash).toBe("#/evaluaciones"));
  });
});
