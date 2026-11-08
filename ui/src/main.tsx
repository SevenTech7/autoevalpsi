import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { obtenerToken } from "./api/token";
import { LimiteDeErrores } from "./componentes/LimiteDeErrores";
import "./estilos.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Falta #raiz en index.html");

createRoot(raiz).render(
  <StrictMode>
    <LimiteDeErrores>
      <App token={obtenerToken()} />
    </LimiteDeErrores>
  </StrictMode>,
);
