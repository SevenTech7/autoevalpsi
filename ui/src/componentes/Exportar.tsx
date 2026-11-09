import { useState } from "react";

import type { Cliente } from "../api/cliente";
import type { Evaluacion } from "../api/tipos";
import { mensajeDe } from "../hooks";
import { abrirCarpetaNativa, elegirCarpetaNativa } from "../puente";
import { Aviso, Boton } from "./base";
import { useDialogos, type OpcionesAviso } from "./Dialogos";

/** Por qué todavía no se puede exportar, en palabras de la usuaria; null si ya se puede. */
export function motivoBloqueo(ev: Evaluacion, cambiosSinGuardar: boolean): string | null {
  if (ev.filas_pendientes > 0) {
    return ev.filas_pendientes === 1
      ? "Falta revisar 1 fila."
      : `Faltan ${ev.filas_pendientes} filas por revisar.`;
  }
  if (!ev.cabecera_revisada) return "Falta confirmar los datos de la hoja.";
  if (cambiosSinGuardar) return "Hay cambios sin confirmar: confírmalos antes de exportar.";
  return null;
}

function nombreDe(ruta: string): string {
  return ruta.split(/[\\/]/).pop() ?? ruta;
}

interface PropsHook {
  api: Cliente;
  evaluacion: Evaluacion;
  cambiosSinGuardar: boolean;
  alExportar: (ev: Evaluacion) => void;
}

/** Lo que comparten el botón de arriba (barra de la revisión) y el panel del pie. */
export function useExportar({ api, evaluacion, cambiosSinGuardar, alExportar }: PropsHook) {
  const { avisar, confirmar } = useDialogos();
  const [iniciales, setIniciales] = useState(false);
  const [borrarFotos, setBorrarFotos] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const bloqueo = motivoBloqueo(evaluacion, cambiosSinGuardar);
  const yaExportada = evaluacion.estado === "exportada";
  const textoBoton = ocupado ? "Exportando…" : yaExportada ? "Exportar de nuevo" : "Exportar a Excel";

  async function exportar() {
    if (
      borrarFotos &&
      !(await confirmar({
        mensaje: "Después de exportar se borrarán las fotos de esta evaluación. ¿Seguro?",
        confirmar: "Sí, exportar y borrar",
        peligro: true,
      }))
    ) {
      return;
    }
    setOcupado(true);
    let resultado: OpcionesAviso;
    try {
      // Primera vez: la usuaria elige dónde guardar (si hay ventana de escritorio para el diálogo).
      const elegir = elegirCarpetaNativa();
      if (elegir && !(await api.configuracion()).carpeta_exportacion && !(await elegir())) {
        resultado = { tipo: "info", mensaje: "No se exportó: elige la carpeta donde guardar los Excel." };
      } else {
        const r = await api.exportar(evaluacion.id, iniciales);
        let extra = "";
        if (borrarFotos) {
          try {
            await api.borrarFotos(evaluacion.id);
          } catch (e) {
            extra = `\n\nLas fotos no se pudieron borrar: ${mensajeDe(e)}`;
          }
        }
        alExportar(await api.evaluacion(evaluacion.id));
        const abrir = abrirCarpetaNativa();
        resultado = {
          tipo: "ok",
          titulo: "Excel exportado",
          mensaje: `Se guardó «${nombreDe(r.evaluacion)}» y se actualizó «${nombreDe(r.consolidado)}» en:\n${r.carpeta}${extra}`,
          accion: abrir ? { texto: "Abrir la carpeta", alHacer: () => void abrir(r.carpeta) } : undefined,
        };
      }
    } catch (e) {
      resultado = { tipo: "error", titulo: "No se pudo exportar", mensaje: mensajeDe(e) };
    } finally {
      setOcupado(false);
    }
    await avisar(resultado);
  }

  return { iniciales, setIniciales, borrarFotos, setBorrarFotos, ocupado, bloqueo, yaExportada, textoBoton, exportar };
}

export type ControlExportar = ReturnType<typeof useExportar>;

/** Exportación (AP-R6): habilitada solo con todo revisado; la primera vez pide la carpeta.
 * El resultado, los errores y las confirmaciones salen en ventanas emergentes. */
export function Exportar(props: PropsHook & { control?: ControlExportar }) {
  const propio = useExportar(props); // sin `control` (uso suelto) el panel lleva su propio estado
  const { iniciales, setIniciales, borrarFotos, setBorrarFotos, ocupado, bloqueo, yaExportada, textoBoton, exportar } =
    props.control ?? propio;

  return (
    <section className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-sm">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <h3 className="text-base font-semibold">Exportar a Excel</h3>
        <label className="flex items-center gap-2 text-base">
          <input
            type="checkbox"
            checked={iniciales}
            onChange={(e) => setIniciales(e.target.checked)}
            className="size-5"
          />
          Usar solo las iniciales del paciente en el nombre del archivo
        </label>
        <label className="flex items-center gap-2 text-base">
          <input
            type="checkbox"
            checked={borrarFotos}
            onChange={(e) => setBorrarFotos(e.target.checked)}
            className="size-5"
          />
          Borrar las fotos de esta evaluación después de exportar
        </label>
        <Boton className="ml-auto" disabled={bloqueo !== null || ocupado} onClick={() => void exportar()}>
          {textoBoton}
        </Boton>
      </div>
      {bloqueo ? (
        <p className="mt-2 text-slate-700">{bloqueo} Cuando esté todo revisado podrás exportar.</p>
      ) : (
        yaExportada && (
          <div className="mt-2">
            <Aviso tipo="info">Esta evaluación ya se exportó. Si exportas de nuevo, se reemplaza su Excel.</Aviso>
          </div>
        )
      )}
    </section>
  );
}
