import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { Boton } from "./base";

/** Ventanas emergentes de la aplicación: avisos, errores y confirmaciones.
 *
 * Todo lo que la usuaria debe leer o decidir tras una acción sale aquí, nunca en la consola ni con
 * los cuadros del navegador (`window.confirm`/`alert`), que en la ventana de escritorio no se
 * pueden dar por seguros. Se muestran de a una; las demás esperan su turno. */

export type TipoAviso = "error" | "ok" | "info";

export interface OpcionesAviso {
  mensaje: string;
  titulo?: string;
  tipo?: TipoAviso;
  /** Un botón extra (p. ej. «Abrir la carpeta»); no cierra la ventana. */
  accion?: { texto: string; alHacer: () => void };
}

export interface OpcionesConfirmar {
  mensaje: string;
  titulo?: string;
  confirmar?: string;
  cancelar?: string;
  /** Acción delicada: el foco empieza en «Cancelar». */
  peligro?: boolean;
}

export interface Dialogos {
  avisar: (o: OpcionesAviso) => Promise<void>;
  confirmar: (o: OpcionesConfirmar) => Promise<boolean>;
}

type Pendiente =
  | { id: number; clase: "aviso"; o: OpcionesAviso; cerrar: () => void }
  | { id: number; clase: "confirmar"; o: OpcionesConfirmar; cerrar: (acepto: boolean) => void };

let siguienteId = 0;

const ContextoDialogos = createContext<Dialogos | null>(null);

export function useDialogos(): Dialogos {
  const d = useContext(ContextoDialogos);
  if (!d) throw new Error("Falta el proveedor de ventanas emergentes");
  return d;
}

/** ¿Hay una ventana emergente abierta? Las teclas de la pantalla de atrás no deben actuar. */
export function hayDialogoAbierto(): boolean {
  return document.querySelector('[role="dialog"], [role="alertdialog"]') !== null;
}

const ESTILO: Record<TipoAviso, { titulo: string; icono: string; color: string }> = {
  error: { titulo: "Algo salió mal", icono: "!", color: "bg-red-100 text-red-700" },
  ok: { titulo: "Listo", icono: "✓", color: "bg-emerald-100 text-emerald-700" },
  info: { titulo: "Aviso", icono: "i", color: "bg-sky-100 text-sky-700" },
};

function Ventana({ actual }: { actual: Pendiente }) {
  const primero = useRef<HTMLButtonElement>(null);
  const esConfirmar = actual.clase === "confirmar";
  const tipo: TipoAviso = actual.clase === "aviso" ? (actual.o.tipo ?? "info") : "info";
  const estilo = ESTILO[tipo];
  const titulo = actual.o.titulo ?? (esConfirmar ? "¿Seguro?" : estilo.titulo);

  const cancelar = useCallback(() => {
    if (actual.clase === "confirmar") actual.cerrar(false);
    else actual.cerrar();
  }, [actual]);

  useEffect(() => {
    primero.current?.focus();
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelar();
      } else if (e.key === "Tab") {
        // el foco se queda dentro de la ventana
        const botones = Array.from(document.querySelectorAll<HTMLElement>("[data-dialogo] button"));
        if (botones.length === 0) return;
        const primeroB = botones[0]!;
        const ultimoB = botones[botones.length - 1]!;
        if (e.shiftKey && document.activeElement === primeroB) {
          e.preventDefault();
          ultimoB.focus();
        } else if (!e.shiftKey && document.activeElement === ultimoB) {
          e.preventDefault();
          primeroB.focus();
        }
      }
    };
    window.addEventListener("keydown", alPulsar, true);
    return () => window.removeEventListener("keydown", alPulsar, true);
  }, [cancelar]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !esConfirmar) cancelar();
      }}
    >
      <div
        data-dialogo
        role={tipo === "error" ? "alertdialog" : "dialog"}
        aria-modal="true"
        aria-labelledby="dialogo-titulo"
        aria-describedby="dialogo-mensaje"
        className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl"
      >
        <div className="flex items-start gap-4">
          <span
            aria-hidden="true"
            className={`flex size-10 shrink-0 items-center justify-center rounded-full text-xl font-bold ${
              esConfirmar ? "bg-amber-100 text-amber-700" : estilo.color
            }`}
          >
            {esConfirmar ? "?" : estilo.icono}
          </span>
          <div className="min-w-0">
            <h2 id="dialogo-titulo" className="text-xl font-semibold">
              {titulo}
            </h2>
            <p id="dialogo-mensaje" className="mt-2 whitespace-pre-line break-words text-base text-slate-700">
              {actual.o.mensaje}
            </p>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          {actual.clase === "aviso" ? (
            <>
              {actual.o.accion && (
                <Boton variante="suave" onClick={actual.o.accion.alHacer}>
                  {actual.o.accion.texto}
                </Boton>
              )}
              <Boton ref={primero} onClick={() => actual.cerrar()}>
                Aceptar
              </Boton>
            </>
          ) : (
            <>
              <Boton
                ref={actual.o.peligro ? primero : undefined}
                variante="suave"
                onClick={() => actual.cerrar(false)}
              >
                {actual.o.cancelar ?? "Cancelar"}
              </Boton>
              <Boton ref={actual.o.peligro ? undefined : primero} onClick={() => actual.cerrar(true)}>
                {actual.o.confirmar ?? "Confirmar"}
              </Boton>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function ProveedorDialogos({ children }: { children: ReactNode }) {
  const [cola, setCola] = useState<Pendiente[]>([]);

  const encolar = useCallback((p: Pendiente) => setCola((c) => [...c, p]), []);
  const sacar = useCallback((p: Pendiente) => setCola((c) => c.filter((x) => x !== p)), []);

  const dialogos = useMemo<Dialogos>(
    () => ({
      avisar: (o) =>
        new Promise<void>((resolver) => {
          const p: Pendiente = {
            id: ++siguienteId,
            clase: "aviso",
            o,
            cerrar: () => {
              sacar(p);
              resolver();
            },
          };
          encolar(p);
        }),
      confirmar: (o) =>
        new Promise<boolean>((resolver) => {
          const p: Pendiente = {
            id: ++siguienteId,
            clase: "confirmar",
            o,
            cerrar: (acepto) => {
              sacar(p);
              resolver(acepto);
            },
          };
          encolar(p);
        }),
    }),
    [encolar, sacar],
  );

  const actual = cola[0];
  return (
    <ContextoDialogos.Provider value={dialogos}>
      {children}
      {actual && <Ventana key={actual.id} actual={actual} />}
    </ContextoDialogos.Provider>
  );
}
