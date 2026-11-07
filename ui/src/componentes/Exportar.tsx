import { useState } from "react";

import type { Cliente } from "../api/cliente";
import type { Evaluacion, ResultadoExportacion } from "../api/tipos";
import { mensajeDe } from "../hooks";
import { abrirCarpetaNativa, elegirCarpetaNativa } from "../puente";
import { Aviso, Boton, Tarjeta } from "./base";

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

interface Props {
  api: Cliente;
  evaluacion: Evaluacion;
  cambiosSinGuardar: boolean;
  alExportar: (ev: Evaluacion) => void;
}

/** Exportación (AP-R6): habilitada solo con todo revisado; la primera vez pide la carpeta. */
export function Exportar({ api, evaluacion, cambiosSinGuardar, alExportar }: Props) {
  const [iniciales, setIniciales] = useState(false);
  const [borrarFotos, setBorrarFotos] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [hecho, setHecho] = useState<ResultadoExportacion | null>(null);
  const abrir = abrirCarpetaNativa();

  const bloqueo = motivoBloqueo(evaluacion, cambiosSinGuardar);
  const yaExportada = evaluacion.estado === "exportada";

  async function exportar() {
    if (borrarFotos && !window.confirm("Después de exportar se borrarán las fotos de esta evaluación. ¿Seguro?")) {
      return;
    }
    setError(null);
    setAviso(null);
    setHecho(null);
    setOcupado(true);
    try {
      // Primera vez: la usuaria elige dónde guardar (si hay ventana de escritorio para el diálogo).
      const elegir = elegirCarpetaNativa();
      if (elegir && !(await api.configuracion()).carpeta_exportacion) {
        if (!(await elegir())) {
          setAviso("No se exportó: elige la carpeta donde guardar los Excel.");
          return;
        }
      }
      const resultado = await api.exportar(evaluacion.id, iniciales);
      setHecho(resultado);
      if (borrarFotos) {
        try {
          await api.borrarFotos(evaluacion.id);
        } catch (e) {
          setAviso(`El Excel quedó guardado, pero no se pudieron borrar las fotos: ${mensajeDe(e)}`);
        }
      }
      alExportar(await api.evaluacion(evaluacion.id));
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Tarjeta titulo="Exportar a Excel">
      <div className="space-y-4">
        {bloqueo ? (
          <Aviso tipo="info">{bloqueo} Cuando esté todo revisado podrás exportar.</Aviso>
        ) : (
          yaExportada && !hecho && <Aviso tipo="info">Esta evaluación ya se exportó. Si exportas de nuevo, se reemplaza su Excel.</Aviso>
        )}
        {error && <Aviso>{error}</Aviso>}
        {aviso && <Aviso tipo="info">{aviso}</Aviso>}
        {hecho && (
          <div className="space-y-3">
            <Aviso tipo="ok">
              Listo: se guardó «{nombreDe(hecho.evaluacion)}» y se actualizó «{nombreDe(hecho.consolidado)}» en{" "}
              <strong className="break-all">{hecho.carpeta}</strong>.
            </Aviso>
            {abrir && (
              <Boton variante="suave" onClick={() => void abrir(hecho.carpeta)}>
                Abrir la carpeta
              </Boton>
            )}
          </div>
        )}
        <div className="space-y-2">
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
        </div>
        <Boton disabled={bloqueo !== null || ocupado} onClick={() => void exportar()}>
          {ocupado ? "Exportando…" : yaExportada ? "Exportar de nuevo" : "Exportar a Excel"}
        </Boton>
      </div>
    </Tarjeta>
  );
}
