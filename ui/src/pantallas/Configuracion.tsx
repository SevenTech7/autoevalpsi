import { useEffect, useRef, useState } from "react";

import type { EstadoActualizacion } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { useDialogos } from "../componentes/Dialogos";
import { mensajeDe, useApi, useCarga } from "../hooks";
import { elegirCarpetaNativa } from "../puente";

function TarjetaCarpeta() {
  const api = useApi();
  const { avisar } = useDialogos();
  const config = useCarga(() => api.configuracion());
  const [escrita, setEscrita] = useState("");
  const nativo = elegirCarpetaNativa();

  const guardada = () =>
    void avisar({ tipo: "ok", titulo: "Carpeta guardada", mensaje: "Listo, la carpeta quedó guardada." });
  const fallo = (e: unknown) =>
    void avisar({ tipo: "error", titulo: "No se pudo guardar la carpeta", mensaje: mensajeDe(e) });

  async function accion(hacer: () => Promise<unknown>) {
    try {
      await hacer();
      guardada();
      config.recargar();
    } catch (e) {
      fallo(e);
    }
  }

  /** El diálogo nativo guarda la carpeta por su cuenta (Puente); cancelar no cambia nada. */
  async function elegirConElDialogo(elegir: () => Promise<string | null>) {
    try {
      if (await elegir()) {
        guardada();
        config.recargar();
      }
    } catch (e) {
      fallo(e);
    }
  }

  return (
    <Tarjeta titulo="Carpeta de los Excel">
      <div className="space-y-4">
        {config.error && <Aviso>{config.error}</Aviso>}
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
  const { avisar, confirmar } = useDialogos();
  const [ocupado, setOcupado] = useState(false);

  async function borrar() {
    setOcupado(true);
    try {
      const exportadas = (await api.evaluaciones()).filter((e) => e.estado === "exportada");
      if (exportadas.length === 0) {
        await avisar({ tipo: "info", mensaje: "Todavía no hay evaluaciones exportadas." });
        return;
      }
      const acepto = await confirmar({
        titulo: "Borrar las fotos",
        mensaje:
          `Se borrarán las fotos de ${exportadas.length} evaluación(es) ya exportada(s). ` +
          "Los Excel y lo que revisaste no se tocan. ¿Seguro?",
        confirmar: "Sí, borrar las fotos",
        peligro: true,
      });
      if (!acepto) return;
      let archivos = 0;
      for (const e of exportadas) archivos += (await api.borrarFotos(e.id)).borrados;
      await avisar({
        tipo: "ok",
        titulo: "Fotos borradas",
        mensaje:
          archivos === 0
            ? "No había fotos que borrar."
            : `Listo: se borraron ${archivos} foto(s) de ${exportadas.length} evaluación(es).`,
      });
    } catch (e) {
      await avisar({ tipo: "error", titulo: "No se pudieron borrar las fotos", mensaje: mensajeDe(e) });
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
        <Boton variante="suave" disabled={ocupado} onClick={() => void borrar()}>
          Borrar las fotos de lo ya exportado
        </Boton>
      </div>
    </Tarjeta>
  );
}

const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;

function TarjetaActualizacion() {
  const api = useApi();
  const { avisar, confirmar } = useDialogos();
  const [ocupado, setOcupado] = useState(false);
  const [estado, setEstado] = useState<EstadoActualizacion | null>(null);
  const avisado = useRef("");

  // Solo se consulta lo local (versión instalada y avance de la descarga); internet, solo al pulsar.
  const local = useCarga(async () => {
    const e = await api.actualizacion();
    setEstado(e);
    return e;
  }, estado?.estado === "descargando" ? 800 : undefined);
  const actual = estado;

  useEffect(() => {
    if (actual?.estado === "error" && actual.mensaje && avisado.current !== actual.mensaje) {
      avisado.current = actual.mensaje;
      void avisar({ tipo: "error", titulo: "No se pudo descargar la actualización", mensaje: actual.mensaje });
    }
  }, [actual, avisar]);

  async function paso(hacer: () => Promise<EstadoActualizacion>, titulo: string) {
    setOcupado(true);
    try {
      setEstado(await hacer());
    } catch (e) {
      await avisar({ tipo: "error", titulo, mensaje: mensajeDe(e) });
    } finally {
      setOcupado(false);
    }
  }

  async function instalar() {
    const acepto = await confirmar({
      titulo: "Instalar la versión nueva",
      mensaje:
        "Windows te pedirá permiso. La aplicación se cerrará, se instalará la versión nueva y volverá a " +
        "abrirse sola. Tus evaluaciones y plantillas se conservan.",
      confirmar: "Instalar ahora",
    });
    if (acepto) await paso(() => api.instalarActualizacion(), "No se pudo instalar la actualización");
  }

  const nueva = actual?.novedad;
  return (
    <Tarjeta titulo="Actualizar la aplicación">
      <div className="space-y-4">
        {local.error && <Aviso>{local.error}</Aviso>}
        {actual && (
          <p>
            Versión instalada: <strong>{actual.actual}</strong>
            {actual.buscada && !nueva && " — ya tienes la última."}
          </p>
        )}
        {nueva && (
          <div className="space-y-2">
            <p>
              Hay una versión nueva: <strong>{nueva.version}</strong> ({mb(nueva.tamano)}).
            </p>
            {nueva.notas && <p className="whitespace-pre-line text-sm text-slate-600">{nueva.notas}</p>}
          </div>
        )}
        {actual?.estado === "descargando" && nueva && (
          <p role="status">
            Descargando… {mb(actual.bajado)} de {mb(nueva.tamano)}
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          {(!nueva || actual?.estado === "error") && (
            <Boton
              variante={nueva ? "suave" : "principal"}
              disabled={ocupado || !actual}
              onClick={() => void paso(() => api.buscarActualizacion(), "No se pudo buscar la actualización")}
            >
              Buscar actualización
            </Boton>
          )}
          {nueva && (actual?.estado === "libre" || actual?.estado === "error") && (
            <Boton
              disabled={ocupado}
              onClick={() => void paso(() => api.descargarActualizacion(), "No se pudo descargar la actualización")}
            >
              Descargar la versión {nueva.version}
            </Boton>
          )}
          {nueva && actual?.estado === "lista" && (
            <Boton disabled={ocupado} onClick={() => void instalar()}>
              Instalar y reiniciar
            </Boton>
          )}
        </div>
        <p className="text-sm text-slate-500">
          Solo busca cuando pulsas el botón; hace falta internet. Nada se instala sin que lo confirmes.
        </p>
      </div>
    </Tarjeta>
  );
}

export function Configuracion() {
  return (
    <div className="space-y-6">
      <TarjetaCarpeta />
      <TarjetaBorrarFotos />
      <TarjetaActualizacion />
    </div>
  );
}
