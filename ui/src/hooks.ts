import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { ErrorApi, type Cliente } from "./api/cliente";

export const ContextoApi = createContext<Cliente | null>(null);

export function useApi(): Cliente {
  const api = useContext(ContextoApi);
  if (!api) throw new Error("Falta el proveedor de la API");
  return api;
}

export function mensajeDe(e: unknown): string {
  if (e instanceof ErrorApi) return e.message;
  return "Algo salió mal. Vuelve a intentarlo.";
}

export interface Carga<T> {
  datos: T | null;
  error: string | null;
  cargando: boolean;
  recargar: () => void;
}

/** Pide datos al montar (y cada `cada` ms si se indica). Un error no borra lo último que llegó. */
export function useCarga<T>(pedir: () => Promise<T>, cada?: number): Carga<T> {
  const [datos, setDatos] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const pedirRef = useRef(pedir);
  pedirRef.current = pedir;

  const recargar = useCallback(() => {
    pedirRef
      .current()
      .then((d) => {
        setDatos(d);
        setError(null);
      })
      .catch((e: unknown) => setError(mensajeDe(e)))
      .finally(() => setCargando(false));
  }, []);

  useEffect(() => {
    recargar();
    if (!cada) return;
    const t = setInterval(recargar, cada);
    return () => clearInterval(t);
  }, [recargar, cada]);

  return { datos, error, cargando, recargar };
}
