import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LimiteDeErrores } from "../componentes/LimiteDeErrores";

afterEach(() => vi.restoreAllMocks());

function Rota(): never {
  throw new Error("algo se rompió al dibujar");
}

describe("límite de errores", () => {
  it("muestra el detalle en vez de dejar la ventana en blanco", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <LimiteDeErrores>
        <Rota />
      </LimiteDeErrores>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("no pudo mostrar esta pantalla");
    expect(screen.getByText("algo se rompió al dibujar")).toBeInTheDocument();
  });

  it("si todo va bien, no se nota", () => {
    render(
      <LimiteDeErrores>
        <p>hola</p>
      </LimiteDeErrores>,
    );
    expect(screen.getByText("hola")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
