import type { ResumenEvaluacion } from "../api/tipos";
import { enlace } from "../ruta";

/** «2026-11-07T10:30:00…» o «2026-11-07» → «07/11/2026». Sin `Date`: evita corrimientos de zona. */
export function fechaLegible(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

const MS_HORA = 3_600_000;

/** Cualquier momento ISO → «07/11/2026 22:35» en hora de Bolivia (UTC−4, sin horario de verano).
 * Sin zona en el texto se toma como ya dado en Bolivia. Se calcula a mano, sin `Intl`: no depende de
 * la base de zonas horarias del navegador ni de la zona de la laptop. */
export function fechaHoraBolivia(iso: string): string {
  const conZona = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}-04:00`;
  const t = new Date(conZona).getTime();
  if (Number.isNaN(t)) return iso;
  const d = new Date(t - 4 * MS_HORA);
  const dos = (n: number) => String(n).padStart(2, "0");
  return `${dos(d.getUTCDate())}/${dos(d.getUTCMonth() + 1)}/${d.getUTCFullYear()} ${dos(d.getUTCHours())}:${dos(d.getUTCMinutes())}`;
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
          <th className="py-2 pr-4 font-medium">Fecha y hora (Bolivia)</th>
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
            <td className="py-3 pr-4">{fechaHoraBolivia(e.creada_en)}</td>
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
