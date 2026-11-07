import { render as base } from "@testing-library/react";
import type { ReactElement } from "react";

import { ProveedorDialogos } from "../componentes/Dialogos";

/** `render` con las ventanas emergentes de la aplicación disponibles, como en la app real. */
export function render(ui: ReactElement, opciones?: Parameters<typeof base>[1]) {
  return base(ui, { wrapper: ProveedorDialogos, ...opciones });
}
