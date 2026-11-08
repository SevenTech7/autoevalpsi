import { useState } from "react";

import type { ResumenEvaluacion } from "../api/tipos";
import { Aviso, Tarjeta } from "../componentes/base";
import { TablaEvaluaciones } from "../componentes/TablaEvaluaciones";
import { useDialogos } from "../componentes/Dialogos";
import { mensajeDe, useApi, useCarga } from "../hooks";

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

export function ListaEvaluaciones({
  evaluaciones,
  alEliminar,
}: {
  evaluaciones: ResumenEvaluacion[];
  alEliminar?: (e: ResumenEvaluacion) => void;
}) {
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
      <TablaEvaluaciones evaluaciones={visibles} alEliminar={alEliminar} />
    </div>
  );
}

export function PantallaEvaluaciones() {
  const api = useApi();
  const { datos, error, recargar } = useCarga(() => api.evaluaciones(), 5000);
  const { confirmar, avisar } = useDialogos();

  async function eliminar(e: ResumenEvaluacion) {
    const nombre = e.paciente || "sin nombre";
    const acepto = await confirmar({
      titulo: "Eliminar la evaluación",
      mensaje:
        `Se elimina la evaluación de «${nombre}» con sus fotos y lo leído. ` +
        "Los Excel que ya exportaste no se tocan. No se puede deshacer.",
      confirmar: "Sí, eliminar",
      peligro: true,
    });
    if (!acepto) return;
    try {
      await api.eliminarEvaluacion(e.id);
      recargar();
    } catch (err) {
      void avisar({ tipo: "error", titulo: "No se pudo eliminar", mensaje: mensajeDe(err) });
    }
  }

  return (
    <Tarjeta titulo="Evaluaciones">
      {error && <Aviso>{error}</Aviso>}
      {datos && <ListaEvaluaciones evaluaciones={datos} alEliminar={(e) => void eliminar(e)} />}
    </Tarjeta>
  );
}
