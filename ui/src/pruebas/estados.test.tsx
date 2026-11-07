import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Cliente } from "../api/cliente";
import type { Evaluacion } from "../api/tipos";
import { TarjetaCelular } from "../pantallas/Inicio";
import { Revision } from "../pantallas/Revision";
import { clienteFalso, evaluacion, fila, inicioVinculo, plantilla } from "./datos";
import { render } from "./render";

/** Pruebas de que la pantalla no se pliega, se reinicia ni pierde el foco por su cuenta. */

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const revisada = (parcial: Partial<Evaluacion> = {}) =>
  evaluacion({
    cabecera_revisada: true,
    filas: [fila({ item: 1 }), fila({ item: 2 }), fila({ item: 3 })],
    filas_pendientes: 0,
    ...parcial,
  });

function montar(ev: Evaluacion, api: Cliente = clienteFalso()) {
  render(
    <Revision api={api} evaluacion={ev} plantilla={plantilla()} alActualizar={vi.fn()} alDescartar={vi.fn()} />,
  );
}

const seccion = () => document.querySelector("details") as HTMLDetailsElement;
/** Lo que hace el navegador cuando la usuaria despliega o pliega: cambia `open` y avisa con `toggle`. */
function alternar(abierta: boolean) {
  seccion().open = abierta;
  fireEvent(seccion(), new Event("toggle"));
}

describe("«Datos de la hoja» no se abre ni se cierra sola", () => {
  it("ya confirmada: la usuaria la abre, escribe y vuelve al valor original, y sigue abierta con el foco", async () => {
    montar(revisada());
    expect(seccion().open).toBe(false);
    alternar(true);
    const campo = screen.getByLabelText("fecha");
    await userEvent.click(campo);
    await userEvent.keyboard("X");
    expect(seccion().open).toBe(true);
    await userEvent.keyboard("{Backspace}"); // vuelve a lo leído: antes esto la plegaba
    expect(seccion().open).toBe(true);
    expect(campo).toHaveFocus();
    expect(campo).toHaveValue("5/11");
  });

  it("sin confirmar: abierta al entrar, y escribir y borrar no la cierra", async () => {
    montar(evaluacion());
    expect(seccion().open).toBe(true);
    const campo = screen.getByLabelText("fecha");
    await userEvent.click(campo);
    await userEvent.keyboard("abc{Backspace}{Backspace}{Backspace}");
    expect(seccion().open).toBe(true);
    expect(campo).toHaveFocus();
  });

  it("si la usuaria la cierra, escribir no la vuelve a abrir (ni al revés)", async () => {
    montar(evaluacion());
    alternar(false);
    expect(seccion().open).toBe(false);
    // se escribe desde el teclado sobre el campo aunque esté plegado en la vista
    fireEvent.change(screen.getByLabelText("fecha"), { target: { value: "otra" } });
    expect(seccion().open).toBe(false);
  });

  it("lo escrito en la cabecera se conserva al confirmar una fila", async () => {
    const ev = evaluacion();
    const corregir = vi.fn().mockResolvedValue({
      ...ev,
      filas: ev.filas.map((f) => (f.item === 2 ? { ...f, revisada: true } : f)),
      filas_pendientes: 1,
    });
    montar(ev, clienteFalso({ corregirEvaluacion: corregir }));
    const campo = screen.getByLabelText("fecha");
    await userEvent.clear(campo);
    await userEvent.type(campo, "9/11");
    await userEvent.click(within(document.querySelector('[data-item="2"]') as HTMLElement).getByRole("button", { name: "Confirmar fila 2" }));
    await waitFor(() => expect(corregir).toHaveBeenCalled());
    expect(screen.getByLabelText("fecha")).toHaveValue("9/11");
    expect(seccion().open).toBe(true);
  });
});

describe("el foco no se pierde al escribir", () => {
  it("una observación conserva el foco y el texto mientras se escribe", async () => {
    montar(evaluacion());
    const caja = screen.getByLabelText(/Observación del ítem 2/);
    await userEvent.click(caja);
    await userEvent.keyboard(" y más");
    expect(caja).toHaveFocus();
    expect(caja).toHaveValue("llega tarde y más");
  });
});

describe("el vínculo del celular", () => {
  it("sigue mirando si ya se vinculó aunque la cuenta regresiva repinte cada segundo", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const vinculo = vi.fn().mockResolvedValue({ vinculado: false, creado: null, ultimo_uso: null });
    const api = clienteFalso({
      vinculo,
      iniciarVinculo: vi.fn().mockResolvedValue(inicioVinculo({ vence_en: 300 })),
    });
    render(<TarjetaCelular sondeoMs={2000} />, {
      wrapper: ({ children }) => <ContextoApiPara api={api}>{children}</ContextoApiPara>,
    });
    fireEvent.click(await screen.findByRole("button", { name: "Vincular celular" }));
    await screen.findByAltText("Código QR para vincular el celular");
    const antes = vinculo.mock.calls.length;
    for (let s = 0; s < 7; s += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000); // cada segundo cambia el contador y repinta
      });
    }
    expect(vinculo.mock.calls.length - antes).toBeGreaterThanOrEqual(2); // 7 s con sondeo cada 2 s
  });
});

import { ProveedorDialogos } from "../componentes/Dialogos";
import { ContextoApi } from "../hooks";
import type { ReactNode } from "react";

function ContextoApiPara({ api, children }: { api: Cliente; children: ReactNode }) {
  return (
    <ContextoApi.Provider value={api}>
      <ProveedorDialogos>{children}</ProveedorDialogos>
    </ContextoApi.Provider>
  );
}
