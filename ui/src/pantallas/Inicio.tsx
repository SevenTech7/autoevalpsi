import { useCallback, useEffect, useRef, useState } from "react";

import type { InicioVinculo } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { useDialogos } from "../componentes/Dialogos";
import { TablaEvaluaciones } from "../componentes/TablaEvaluaciones";
import { mensajeDe, useApi, useCarga } from "../hooks";
import { enlace } from "../ruta";

export function formatearRestante(segundos: number): string {
  const m = Math.floor(segundos / 60);
  const s = segundos % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function urlQr(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** Vincular el celular (AP-D2): un código de un solo uso que vence en 5 minutos. */
export function TarjetaCelular({ sondeoMs = 2000 }: { sondeoMs?: number }) {
  const api = useApi();
  const { avisar, confirmar } = useDialogos();
  const vinculo = useCarga(() => api.vinculo());
  const recargarVinculo = vinculo.recargar; // estable; `vinculo` es un objeto nuevo en cada render
  const [sesion, setSesion] = useState<InicioVinculo | null>(null);
  const [restante, setRestante] = useState(0);
  const [ocupado, setOcupado] = useState(false);
  const creadoPrevio = useRef<string | null>(null);

  const iniciar = useCallback(
    async (ip?: string) => {
      setOcupado(true);
      try {
        if (!sesion) creadoPrevio.current = (await api.vinculo()).creado;
        const nueva = await api.iniciarVinculo(ip);
        if (!nueva.qr_svg) {
          setSesion(null);
          void avisar({
            tipo: "error",
            titulo: "No se pudo preparar el código",
            mensaje: nueva.mensaje || "No se pudo preparar el código.",
          });
          return;
        }
        setSesion(nueva);
        setRestante(Math.ceil(nueva.vence_en));
      } catch (e) {
        void avisar({ tipo: "error", titulo: "No se pudo preparar el código", mensaje: mensajeDe(e) });
      } finally {
        setOcupado(false);
      }
    },
    [api, sesion, avisar],
  );

  // Cuenta regresiva del código.
  const hayCodigo = sesion !== null && restante > 0;
  useEffect(() => {
    if (!hayCodigo) return;
    const t = setInterval(() => setRestante((r) => Math.max(0, r - 1)), 1000);
    return () => clearInterval(t);
  }, [hayCodigo]);

  // Mientras el QR está a la vista, mirar si el celular ya lo canjeó.
  useEffect(() => {
    if (!hayCodigo) return;
    const t = setInterval(() => {
      api
        .vinculo()
        .then((v) => {
          if (v.vinculado && v.creado !== creadoPrevio.current) {
            setSesion(null);
            recargarVinculo();
            void avisar({
              tipo: "ok",
              titulo: "Celular vinculado",
              mensaje: "¡Listo! El celular quedó vinculado.",
            });
          }
        })
        .catch(() => undefined); // un fallo del sondeo no molesta: el siguiente lo reintenta
    }, sondeoMs);
    return () => clearInterval(t);
  }, [hayCodigo, api, sondeoMs, recargarVinculo, avisar]);

  async function desvincular() {
    const acepto = await confirmar({
      titulo: "Desvincular el celular",
      mensaje: "Para enviar fotos tendrás que vincularlo de nuevo.",
      confirmar: "Sí, desvincular",
      peligro: true,
    });
    if (!acepto) return;
    try {
      await api.desvincular();
      recargarVinculo();
    } catch (e) {
      void avisar({ tipo: "error", titulo: "No se pudo desvincular", mensaje: mensajeDe(e) });
    }
  }

  const vinculado = vinculo.datos?.vinculado ?? false;
  return (
    <Tarjeta titulo="Celular">
      <div className="space-y-4">
        {sesion?.qr_svg && (
          <div className="flex flex-wrap items-start gap-6">
            {restante > 0 ? (
              <img
                src={urlQr(sesion.qr_svg)}
                alt="Código QR para vincular el celular"
                className="h-56 w-56 rounded-lg border border-slate-200"
              />
            ) : (
              <Aviso tipo="info">El código venció. Pide uno nuevo.</Aviso>
            )}
            <div className="max-w-md space-y-3">
              <ol className="list-decimal space-y-1 pl-5">
                <li>Conecta el celular al mismo WiFi que esta laptop.</li>
                <li>Abre la cámara del celular y apunta al código.</li>
                <li>Toca el aviso que aparece y espera el mensaje de «vinculado».</li>
              </ol>
              {restante > 0 && (
                <p className="text-slate-600">
                  El código vence en <strong>{formatearRestante(restante)}</strong> y solo sirve una vez.
                </p>
              )}
              {sesion.ips.length > 1 && (
                <label className="block text-sm text-slate-700">
                  Red de la laptop
                  <select
                    className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                    value={sesion.ip ?? ""}
                    disabled={ocupado}
                    onChange={(e) => void iniciar(e.target.value)}
                  >
                    {sesion.ips.map((ip) => (
                      <option key={ip} value={ip}>
                        {ip}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>
        )}

        {!sesion && (
          <p>
            {vinculado
              ? "Hay un celular vinculado con esta laptop."
              : "Todavía no hay ningún celular vinculado. Vincúlalo para enviar fotos."}
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <Boton disabled={ocupado} onClick={() => void iniciar(sesion?.ip ?? undefined)}>
            {sesion ? "Código nuevo" : vinculado ? "Vincular otro celular" : "Vincular celular"}
          </Boton>
          {vinculado && !sesion && (
            <Boton variante="suave" onClick={() => void desvincular()}>
              Desvincular
            </Boton>
          )}
        </div>
        {vinculado && !sesion && (
          <p className="text-sm text-slate-600">
            Solo puede haber un celular: si vinculas otro, el anterior deja de funcionar.
          </p>
        )}

        <details className="text-slate-700">
          <summary className="cursor-pointer font-medium">¿El celular no se conecta?</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>El celular y la laptop deben estar en el mismo WiFi (no en datos móviles).</li>
            <li>
              En Windows, el WiFi de la casa debe estar como red <strong>Privada</strong>: Configuración →
              Red e Internet → WiFi → propiedades de la red.
            </li>
            <li>Si cambias de red o la laptop cambia de IP, vuelve a vincular el celular.</li>
          </ul>
        </details>
      </div>
    </Tarjeta>
  );
}

export function TarjetaPendientes({ sondeoMs = 3000 }: { sondeoMs?: number }) {
  const api = useApi();
  const cola = useCarga(() => api.cola(), sondeoMs);
  const evaluaciones = useCarga(() => api.evaluaciones(), sondeoMs);
  const porTerminar = (evaluaciones.datos ?? []).filter((e) => e.estado !== "exportada");
  const leyendo = cola.datos?.pendientes ?? 0;

  return (
    <Tarjeta
      titulo="Evaluaciones por terminar"
      acciones={
        <a className="text-acento underline" href={enlace.evaluaciones}>
          Ver todas
        </a>
      }
    >
      <div className="space-y-4">
        {leyendo > 0 && (
          <Aviso tipo="info">
            {leyendo === 1 ? "Estoy leyendo 1 foto…" : `Estoy leyendo ${leyendo} fotos…`}
          </Aviso>
        )}
        {evaluaciones.error && <Aviso>{evaluaciones.error}</Aviso>}
        {evaluaciones.datos &&
          (porTerminar.length === 0 ? (
            <p className="text-slate-600">No hay nada pendiente. Las fotos nuevas aparecerán aquí.</p>
          ) : (
            <TablaEvaluaciones evaluaciones={porTerminar.slice(0, 5)} />
          ))}
      </div>
    </Tarjeta>
  );
}

export function Inicio() {
  return (
    <div className="space-y-6">
      <TarjetaCelular />
      <TarjetaPendientes />
    </div>
  );
}
