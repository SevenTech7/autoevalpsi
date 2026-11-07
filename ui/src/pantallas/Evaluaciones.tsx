import { useState } from "react";

import type { ResumenEvaluacion } from "../api/tipos";
import { Aviso, Tarjeta } from "../componentes/base";
import { TablaEvaluaciones } from "../componentes/TablaEvaluaciones";
import { useApi, useCarga } from "../hooks";
import { enlace } from "../ruta";

export type Filtro = "todas" | "por_revisar" | "listas" | "exportadas";

const FILTROS: { id: Filtro; texto: string }[] = [
  { id: "todas", texto: "Todas" },
  { id: "por_revisar", texto: "Por revisar" },
  { id: "listas", texto: "Listas para exportar" },
  { id: "exportadas", texto: "Exportadas" },
];

const ESTADO_DEL_FILTRO: Record<Exclude<Filtro, "todas">, ResumenEvaluacion["estado"]> = {
  por_revisar: "pendiente",
  listas: "revisada",
  exportadas: "exportada",
};

export function filtrar(evaluaciones: ResumenEvaluacion[], filtro: Filtro): ResumenEvaluacion[] {
  return filtro === "todas" ? evaluaciones : evaluaciones.filter((e) => e.estado === ESTADO_DEL_FILTRO[filtro]);
}

export function ListaEvaluaciones({ evaluaciones }: { evaluaciones: ResumenEvaluacion[] }) {
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const visibles = filtrar(evaluaciones, filtro);
  return (
    <div className="space-y-4">
      <div role="group" aria-label="Filtrar evaluaciones" className="flex flex-wrap gap-2">
        {FILTROS.map((f) => {
          const cuantas = filtrar(evaluaciones, f.id).length;
          return (
            <button
              key={f.id}
              type="button"
              aria-pressed={filtro === f.id}
              onClick={() => setFiltro(f.id)}
              className={`rounded-full border px-4 py-1.5 text-base ${
                filtro === f.id
                  ? "border-acento bg-acento text-white"
                  : "border-slate-300 bg-white hover:bg-slate-50"
              }`}
            >
              {f.texto} ({cuantas})
            </button>
          );
        })}
      </div>
      <TablaEvaluaciones evaluaciones={visibles} />
    </div>
  );
}

export function PantallaEvaluaciones() {
  const api = useApi();
  const { datos, error } = useCarga(() => api.evaluaciones(), 5000);
  return (
    <Tarjeta titulo="Evaluaciones">
      {error && <Aviso>{error}</Aviso>}
      {datos && <ListaEvaluaciones evaluaciones={datos} />}
    </Tarjeta>
  );
}

/** Marcador hasta AP-R5 (pantalla de revisión). */
export function PantallaEvaluacion({ id }: { id: string }) {
  return (
    <Tarjeta titulo="Revisión">
      <p className="mb-4">
        La pantalla para revisar la evaluación <code>{id}</code> llega en la siguiente etapa.
      </p>
      <a className="text-acento underline" href={enlace.evaluaciones}>
        Volver a la lista
      </a>
    </Tarjeta>
  );
}
