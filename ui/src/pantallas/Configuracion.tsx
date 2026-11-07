import { useState } from "react";

import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { mensajeDe, useApi, useCarga } from "../hooks";

/** Lo que el escritorio (pywebview) expone en `window.pywebview.api` (app/escritorio.py: Puente). */
interface PuenteEscritorio {
  elegir_carpeta_exportacion: () => Promise<string | null>;
}

function puente(): PuenteEscritorio | null {
  const api = (window as unknown as { pywebview?: { api?: Partial<PuenteEscritorio> } }).pywebview?.api;
  return api?.elegir_carpeta_exportacion ? (api as PuenteEscritorio) : null;
}

function TarjetaCarpeta() {
  const api = useApi();
  const config = useCarga(() => api.configuracion());
  const [escrita, setEscrita] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardada, setGuardada] = useState(false);
  const nativo = puente();

  async function accion(hacer: () => Promise<unknown>) {
    setError(null);
    setGuardada(false);
    try {
      await hacer();
      setGuardada(true);
      config.recargar();
    } catch (e) {
      setError(mensajeDe(e));
    }
  }

  /** El diálogo nativo guarda la carpeta por su cuenta (Puente); cancelar no cambia nada. */
  async function elegirConElDialogo(escritorio: PuenteEscritorio) {
    setError(null);
    setGuardada(false);
    try {
      if (await escritorio.elegir_carpeta_exportacion()) {
        setGuardada(true);
        config.recargar();
      }
    } catch (e) {
      setError(mensajeDe(e));
    }
  }

  return (
    <Tarjeta titulo="Carpeta de los Excel">
      <div className="space-y-4">
        {config.error && <Aviso>{config.error}</Aviso>}
        {error && <Aviso>{error}</Aviso>}
        {guardada && <Aviso tipo="ok">Listo, la carpeta quedó guardada.</Aviso>}
        {config.datos && (
          <p>
            Los Excel se guardan en: <strong className="break-all">{config.datos.carpeta_exportacion_efectiva}</strong>
            {!config.datos.carpeta_exportacion && " (carpeta por defecto)"}
          </p>
        )}
        {nativo ? (
          <Boton onClick={() => void elegirConElDialogo(nativo)}>Elegir otra carpeta…</Boton>
        ) : (
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void accion(() => api.guardarCarpetaExportacion(escrita));
            }}
          >
            <label className="grow text-sm text-slate-700">
              Ruta de la carpeta
              <input
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
                value={escrita}
                placeholder="C:\Users\…\Documentos\Excel"
                onChange={(e) => setEscrita(e.target.value)}
              />
            </label>
            <Boton type="submit" disabled={!escrita.trim()}>
              Guardar
            </Boton>
          </form>
        )}
        {config.datos?.carpeta_exportacion && (
          <Boton variante="suave" onClick={() => void accion(() => api.guardarCarpetaExportacion(""))}>
            Volver a la carpeta por defecto
          </Boton>
        )}
      </div>
    </Tarjeta>
  );
}

function TarjetaBorrarFotos() {
  const api = useApi();
  const [resultado, setResultado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function borrar() {
    setError(null);
    setResultado(null);
    setOcupado(true);
    try {
      const exportadas = (await api.evaluaciones()).filter((e) => e.estado === "exportada");
      if (exportadas.length === 0) {
        setResultado("Todavía no hay evaluaciones exportadas.");
        return;
      }
      if (
        !window.confirm(
          `Se borrarán las fotos de ${exportadas.length} evaluación(es) ya exportada(s). ` +
            "Los Excel y lo que revisaste no se tocan. ¿Seguro?",
        )
      ) {
        return;
      }
      let archivos = 0;
      for (const e of exportadas) archivos += (await api.borrarFotos(e.id)).borrados;
      setResultado(
        archivos === 0
          ? "No había fotos que borrar."
          : `Listo: se borraron ${archivos} foto(s) de ${exportadas.length} evaluación(es).`,
      );
    } catch (e) {
      setError(mensajeDe(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Tarjeta titulo="Fotos guardadas">
      <div className="space-y-4">
        <p>
          La aplicación guarda las fotos en esta laptop y no las borra sola. Cuando ya no las necesites, puedes
          borrar las de las evaluaciones que ya exportaste.
        </p>
        {error && <Aviso>{error}</Aviso>}
        {resultado && <Aviso tipo="ok">{resultado}</Aviso>}
        <Boton variante="suave" disabled={ocupado} onClick={() => void borrar()}>
          Borrar las fotos de lo ya exportado
        </Boton>
      </div>
    </Tarjeta>
  );
}

export function Configuracion() {
  return (
    <div className="space-y-6">
      <TarjetaCarpeta />
      <TarjetaBorrarFotos />
    </div>
  );
}
