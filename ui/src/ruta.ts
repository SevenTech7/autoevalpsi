import { useCallback, useEffect, useState } from "react";

/** Navegación por `#/…`: el servidor solo sirve `/`, así no hace falta que reescriba rutas. */
export type Ruta =
  | { pantalla: "inicio" }
  | { pantalla: "evaluaciones" }
  | { pantalla: "evaluacion"; id: string }
  | { pantalla: "configuracion" };

export function analizarRuta(hash: string): Ruta {
  const partes = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [primera, id] = partes;
  if (primera === "evaluaciones") {
    return id ? { pantalla: "evaluacion", id: decodeURIComponent(id) } : { pantalla: "evaluaciones" };
  }
  if (primera === "configuracion") return { pantalla: "configuracion" };
  return { pantalla: "inicio" };
}

export const enlace = {
  inicio: "#/",
  evaluaciones: "#/evaluaciones",
  evaluacion: (id: string) => `#/evaluaciones/${encodeURIComponent(id)}`,
  configuracion: "#/configuracion",
};

export function useRuta(): Ruta {
  const [ruta, setRuta] = useState<Ruta>(() => analizarRuta(window.location.hash));
  const alCambiar = useCallback(() => setRuta(analizarRuta(window.location.hash)), []);
  useEffect(() => {
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, [alCambiar]);
  return ruta;
}
