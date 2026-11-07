import type { ResumenEvaluacion } from "../api/tipos";
import { enlace } from "../ruta";

/** «2026-11-07T10:30:00…» o «2026-11-07» → «07/11/2026». Sin `Date`: evita corrimientos de zona. */
export function fechaLegible(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export function describirEstado(e: ResumenEvaluacion): string {
  if (e.estado === "exportada") return "Exportada";
  if (e.estado === "revisada") return "Lista para exportar";
  if (e.filas_pendientes > 0) {
    return e.filas_pendientes === 1
      ? "Falta revisar 1 fila"
      : `Faltan ${e.filas_pendientes} filas por revisar`;
  }
  return "Falta confirmar la cabecera";
}

const colorEstado: Record<ResumenEvaluacion["estado"], string> = {
  pendiente: "bg-amber-100 text-amber-900",
  revisada: "bg-emerald-100 text-emerald-900",
  exportada: "bg-slate-100 text-slate-700",
};

export function TablaEvaluaciones({ evaluaciones }: { evaluaciones: ResumenEvaluacion[] }) {
  if (evaluaciones.length === 0) {
    return <p className="text-slate-600">No hay evaluaciones todavía.</p>;
  }
  return (
    <table className="w-full border-collapse text-left">
      <thead>
        <tr className="border-b border-slate-200 text-sm text-slate-600">
          <th className="py-2 pr-4 font-medium">Paciente</th>
          <th className="py-2 pr-4 font-medium">Fecha</th>
          <th className="py-2 pr-4 font-medium">Formulario</th>
          <th className="py-2 font-medium">Estado</th>
        </tr>
      </thead>
      <tbody>
        {evaluaciones.map((e) => (
          <tr key={e.id} className="border-b border-slate-100">
            <td className="py-3 pr-4">
              <a className="font-medium text-acento underline" href={enlace.evaluacion(e.id)}>
                {e.paciente || "Sin nombre"}
              </a>
            </td>
            <td className="py-3 pr-4">{fechaLegible(e.fecha || e.creada_en)}</td>
            <td className="py-3 pr-4">{e.plantilla_id}</td>
            <td className="py-3">
              <span className={`rounded-full px-3 py-1 text-sm ${colorEstado[e.estado]}`}>
                {describirEstado(e)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
