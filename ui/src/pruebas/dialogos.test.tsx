import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { useDialogos, type Dialogos } from "../componentes/Dialogos";
import { render } from "./render";

/** Expone las ventanas al test para abrirlas como lo haría una pantalla. */
function montar() {
  const caja: { d?: Dialogos } = {};
  function Captura() {
    caja.d = useDialogos();
    return null;
  }
  render(<Captura />);
  return () => caja.d!;
}

describe("ventanas emergentes", () => {
  it("confirmar devuelve true al aceptar y false al cancelar", async () => {
    const dialogos = montar();
    let respuesta: Promise<boolean>;
    act(() => {
      respuesta = dialogos().confirmar({ mensaje: "¿Seguro?", confirmar: "Sí, seguro" });
    });
    expect(await screen.findByRole("dialog")).toHaveTextContent("¿Seguro?");
    await userEvent.click(screen.getByRole("button", { name: "Sí, seguro" }));
    await expect(respuesta!).resolves.toBe(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    act(() => {
      respuesta = dialogos().confirmar({ mensaje: "¿Otra vez?" });
    });
    await userEvent.click(await screen.findByRole("button", { name: "Cancelar" }));
    await expect(respuesta!).resolves.toBe(false);
  });

  it("Escape cancela una confirmación y cierra un aviso", async () => {
    const dialogos = montar();
    let c: Promise<boolean>;
    let a: Promise<void>;
    act(() => {
      c = dialogos().confirmar({ mensaje: "¿Seguro?" });
    });
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    await expect(c!).resolves.toBe(false);

    act(() => {
      a = dialogos().avisar({ mensaje: "Hola", tipo: "info" });
    });
    await screen.findByRole("dialog");
    await userEvent.keyboard("{Escape}");
    await expect(a!).resolves.toBeUndefined();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("un error es un alertdialog con su título y el mensaje", async () => {
    const dialogos = montar();
    act(() => {
      void dialogos().avisar({ tipo: "error", mensaje: "No hay conexión." });
    });
    const popup = await screen.findByRole("alertdialog");
    expect(popup).toHaveTextContent("Algo salió mal");
    expect(popup).toHaveTextContent("No hay conexión.");
  });

  it("el foco empieza en el botón principal, o en «Cancelar» si la acción es delicada", async () => {
    const dialogos = montar();
    act(() => {
      void dialogos().confirmar({ mensaje: "Normal", confirmar: "Hacerlo" });
    });
    await screen.findByRole("dialog");
    expect(screen.getByRole("button", { name: "Hacerlo" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");

    act(() => {
      void dialogos().confirmar({ mensaje: "Borra cosas", confirmar: "Borrar", peligro: true });
    });
    await screen.findByRole("dialog");
    expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
  });

  it("las ventanas salen de a una, en orden", async () => {
    const dialogos = montar();
    act(() => {
      void dialogos().avisar({ mensaje: "Primero", tipo: "ok" });
      void dialogos().avisar({ mensaje: "Segundo", tipo: "ok" });
    });
    expect(await screen.findByRole("dialog")).toHaveTextContent("Primero");
    expect(screen.queryByText("Segundo")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Aceptar" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Segundo");
  });

  it("la acción extra no cierra la ventana", async () => {
    const dialogos = montar();
    let veces = 0;
    act(() => {
      void dialogos().avisar({
        mensaje: "Guardado",
        tipo: "ok",
        accion: { texto: "Abrir la carpeta", alHacer: () => (veces += 1) },
      });
    });
    await userEvent.click(await screen.findByRole("button", { name: "Abrir la carpeta" }));
    expect(veces).toBe(1);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("Tab no saca el foco de la ventana", async () => {
    const dialogos = montar();
    act(() => {
      void dialogos().confirmar({ mensaje: "¿Seguro?", confirmar: "Sí" });
    });
    await screen.findByRole("dialog");
    expect(screen.getByRole("button", { name: "Sí" })).toHaveFocus();
    await userEvent.tab(); // último botón: vuelve al primero
    expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();
  });
});
