import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { Cliente } from "../api/cliente";
import type { Evaluacion, FilaGuardada, PaginaGuardada, Plantilla } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { Exportar } from "../componentes/Exportar";
import { fechaLegible } from "../componentes/TablaEvaluaciones";
import { mensajeDe, useApi, useCarga } from "../hooks";
import { enlace } from "../ruta";

/** Lo que cada bandera del lector significa, en palabras de la usuaria. */
export const TEXTO_BANDERA: Record<string, string> = {
  sin_marca: "No se ve ninguna marca",
  doble_marca: "Hay más de una marca",
  contraste_bajo: "La marca se ve muy tenue",
  registro_dudoso: "La foto no calzó bien con el formulario",
  ocr_confianza_baja: "El texto leído es dudoso",
  ocr_sin_texto: "No se pudo leer el texto",
  ocr_error: "Falló la lectura del texto",
  cabecera_vacia: "No se leyó este campo",
};

export function describirBandera(b: string): string {
  return TEXTO_BANDERA[b] ?? b;
}

export function textoFaltan(n: number): string {
  if (n === 0) return "Todas las filas están revisadas";
  return n === 1 ? "Falta revisar 1 fila" : `Faltan ${n} filas por revisar`;
}

interface Borrador {
  opcion?: string | null;
  observacion?: string;
}

interface InfoItem {
  texto: string;
  opciones: string[];
}

function infoDeItems(plantilla: Plantilla): Map<number, InfoItem> {
  const mapa = new Map<number, InfoItem>();
  for (const p of plantilla.paginas) {
    for (const t of p.tablas) {
      for (const f of t.filas) mapa.set(f.item, { texto: f.texto, opciones: t.opciones });
    }
  }
  return mapa;
}

/** Campos de cabecera distintos del paciente, en el orden de la plantilla, más los que ya vengan leídos. */
export function camposDeCabecera(plantilla: Plantilla, evaluacion: Evaluacion): string[] {
  const campos: string[] = [];
  for (const p of plantilla.paginas) {
    for (const c of p.cabecera) if (c.campo !== "paciente" && !campos.includes(c.campo)) campos.push(c.campo);
  }
  for (const k of Object.keys(evaluacion.cabecera)) if (!campos.includes(k)) campos.push(k);
  return campos;
}

/** ¿Hay columna de observaciones? Si la plantilla la declara o ya hay algo leído o escrito. */
export function hayObservaciones(plantilla: Plantilla, filas: FilaGuardada[]): boolean {
  const declarada = plantilla.paginas.some((p) => p.tablas.some((t) => t.observacion_x));
  return declarada || filas.some((f) => f.ruta_recorte || f.texto_ocr || f.observacion);
}

// --- iconos de aviso -----------------------------------------------------------------------------

type Dibujo = { color: string; trazo: ReactNode };

const DIBUJOS: Record<string, Dibujo> = {
  // círculo punteado: no hay marca
  sin_marca: {
    color: "text-slate-600",
    trazo: <circle cx="12" cy="12" r="8" strokeDasharray="3 3" />,
  },
  // triángulo con signo de exclamación: más de una marca
  doble_marca: {
    color: "text-amber-600",
    trazo: (
      <>
        <path d="M12 4 21 20H3z" />
        <path d="M12 10v4M12 17v.5" />
      </>
    ),
  },
  // círculo a medias: marca tenue
  contraste_bajo: {
    color: "text-amber-500",
    trazo: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
      </>
    ),
  },
  // marco con cruz: la foto no calzó con el formulario
  registro_dudoso: {
    color: "text-red-600",
    trazo: (
      <>
        <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
        <path d="M9 9l6 6M15 9l-6 6" />
      </>
    ),
  },
  // letra T: lectura del texto manuscrito
  ocr: {
    color: "text-sky-600",
    trazo: <path d="M5 7V5h14v2M12 5v14M9 19h6" />,
  },
};

const DIBUJO_GENERICO: Dibujo = {
  color: "text-slate-500",
  trazo: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 11v5M12 8v.5" />
    </>
  ),
};

function dibujoDe(bandera: string): Dibujo {
  if (bandera.startsWith("ocr_")) return DIBUJOS.ocr!;
  return DIBUJOS[bandera] ?? DIBUJO_GENERICO;
}

/** Icono de aviso: el motivo aparece al pasar el ratón o al enfocarlo con el teclado. */
export function IconoAviso({ bandera }: { bandera: string }) {
  const { color, trazo } = dibujoDe(bandera);
  return (
    <span className="group relative inline-flex cursor-help rounded p-0.5" tabIndex={0}>
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className={`size-5 fill-none stroke-current ${color}`}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {trazo}
      </svg>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-full z-30 mt-1 w-max max-w-60 -translate-x-1/2 rounded-md bg-slate-900 px-2 py-1 text-sm text-white opacity-0 shadow-lg transition-opacity group-hover:opacity-100 group-focus:opacity-100"
      >
        {describirBandera(bandera)}
      </span>
    </span>
  );
}

// --- cabecera -----------------------------------------------------------------------------------

function Recorte({ src, alt, clase }: { src: string; alt: string; clase: string }) {
  const [roto, setRoto] = useState(false);
  if (roto) return <span className="text-sm text-slate-500">Sin imagen guardada.</span>;
  return (
    <img
      src={src}
      alt={alt}
      onError={() => setRoto(true)}
      className={`rounded border border-slate-200 bg-white object-contain ${clase}`}
    />
  );
}

interface PropsCabecera {
  api: Cliente;
  evaluacion: Evaluacion;
  campos: string[];
  guardando: boolean;
  alConfirmar: (paciente: string, cabecera: Record<string, string>) => void;
  alCambiarEstado: (sinConfirmar: boolean) => void;
}

function Cabecera({ api, evaluacion, campos, guardando, alConfirmar, alCambiarEstado }: PropsCabecera) {
  const [paciente, setPaciente] = useState(evaluacion.paciente);
  const [valores, setValores] = useState<Record<string, string>>(evaluacion.cabecera);
  const cambiada =
    paciente !== evaluacion.paciente || campos.some((c) => (valores[c] ?? "") !== (evaluacion.cabecera[c] ?? ""));
  useEffect(() => {
    alCambiarEstado(cambiada);
    return () => alCambiarEstado(false);
  }, [cambiada, alCambiarEstado]);
  const confirmada = evaluacion.cabecera_revisada && !cambiada;

  const campo = (clave: string, etiqueta: string, valor: string, poner: (v: string) => void) => (
    <div key={clave} className="min-w-0">
      <label className="block text-sm font-medium text-slate-700" htmlFor={`cab-${clave}`}>
        {etiqueta}
      </label>
      {evaluacion.recortes_cabecera[clave] && (
        <Recorte
          src={api.urlRecorteCabecera(evaluacion.id, clave)}
          alt={`Lo escrito en «${etiqueta}»`}
          clase="mb-1 max-h-9 max-w-full"
        />
      )}
      <input
        id={`cab-${clave}`}
        value={valor}
        onChange={(e) => poner(e.target.value)}
        className="w-full rounded-md border border-slate-300 px-2 py-1 text-base"
      />
    </div>
  );

  return (
    <details open={!confirmada} className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <summary className="flex cursor-pointer flex-wrap items-center gap-3 px-3 py-2 text-base font-semibold">
        Datos de la hoja
        {confirmada ? (
          <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-sm font-normal text-emerald-900">
            Confirmados
          </span>
        ) : (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-normal text-amber-900">
            Sin confirmar
          </span>
        )}
        <span className="text-sm font-normal text-slate-600">
          {fechaLegible(evaluacion.fecha)} · lo leído de la letra puede tener errores
        </span>
      </summary>
      <div className="flex flex-wrap items-end gap-x-4 gap-y-2 border-t border-slate-100 px-3 py-2">
        <div className="grid min-w-0 flex-1 grid-cols-[repeat(auto-fit,minmax(13rem,1fr))] gap-x-4 gap-y-2">
          {campo("paciente", "Paciente", paciente, setPaciente)}
          {campos.map((c) => campo(c, c, valores[c] ?? "", (v) => setValores({ ...valores, [c]: v })))}
        </div>
        <Boton
          disabled={guardando || confirmada}
          onClick={() => alConfirmar(paciente, Object.fromEntries(campos.map((c) => [c, valores[c] ?? ""])))}
        >
          Confirmar datos de la hoja
        </Boton>
      </div>
    </details>
  );
}

// --- una fila de la tabla -----------------------------------------------------------------------

interface PropsFila {
  api: Cliente;
  evaluacionId: string;
  fila: FilaGuardada;
  info: InfoItem | undefined;
  borrador: Borrador | undefined;
  activa: boolean;
  guardando: boolean;
  conObservaciones: boolean;
  alElegir: () => void;
  alCambiarOpcion: (opcion: string | null) => void;
  alCambiarObservacion: (texto: string) => void;
  alConfirmar: () => void;
}

const CELDA = "border-b border-slate-200 px-1 py-0.5 align-middle";

function FilaTabla(p: PropsFila) {
  const { fila, info, borrador, activa } = p;
  const opciones = info?.opciones ?? [];
  const opcion = borrador && "opcion" in borrador ? (borrador.opcion ?? null) : fila.opcion;
  const observacion = borrador?.observacion ?? fila.observacion;
  const cambiada = borrador !== undefined && Object.keys(borrador).length > 0;
  const ref = useRef<HTMLTableRowElement>(null);

  useEffect(() => {
    if (activa) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [activa]);

  const hecha = fila.revisada && !cambiada;
  const fondo = activa ? "bg-sky-50" : hecha ? "bg-white" : "bg-amber-50";

  const elegir = (valor: string | null) => {
    p.alElegir();
    p.alCambiarOpcion(valor);
  };

  return (
    <tr
      ref={ref}
      aria-current={activa ? "true" : undefined}
      data-item={fila.item}
      onClick={p.alElegir}
      className={`${fondo} ${activa ? "outline outline-2 -outline-offset-2 outline-acento" : ""}`}
    >
      <th scope="row" className={`${CELDA} pl-2 pr-3 text-left font-normal`}>
        <span className="mr-2 inline-block min-w-6 font-semibold text-slate-500">{fila.item}.</span>
        <span title={info?.texto}>{info?.texto || `Ítem ${fila.item}`}</span>
      </th>

      {opciones.map((o, n) => {
        const elegida = opcion === o;
        const leida = fila.opcion_leida === o && !elegida;
        return (
          <td key={o} className={`${CELDA} text-center`}>
            <button
              type="button"
              role="radio"
              aria-checked={elegida}
              aria-label={o}
              title={`${n + 1} · ${o}${leida ? " (lo que leyó la aplicación)" : ""}`}
              onClick={() => elegir(o)}
              className={`mx-auto flex size-7 items-center justify-center rounded-full border-2 text-sm font-semibold ${
                elegida
                  ? "border-acento bg-acento text-white"
                  : leida
                    ? "border-dashed border-slate-400 bg-white text-slate-400"
                    : "border-slate-300 bg-white text-transparent hover:border-acento hover:text-slate-300"
              }`}
            >
              {elegida ? "✓" : n + 1}
            </button>
          </td>
        );
      })}

      <td className={`${CELDA} text-center`}>
        <button
          type="button"
          role="radio"
          aria-checked={opcion === null}
          aria-label="Sin respuesta"
          title="0 · Sin respuesta"
          onClick={() => elegir(null)}
          className={`mx-auto flex h-7 min-w-7 items-center justify-center rounded-full border-2 px-1 text-sm ${
            opcion === null
              ? "border-slate-700 bg-slate-700 text-white"
              : "border-slate-300 bg-white text-slate-400 hover:border-slate-500"
          }`}
        >
          {opcion === null ? "—" : "0"}
        </button>
      </td>

      <td className={`${CELDA} text-center`}>
        <span className="inline-flex items-center justify-center gap-0.5">
          {fila.banderas.map((b) => (
            <IconoAviso key={b} bandera={b} />
          ))}
        </span>
      </td>

      {p.conObservaciones && (
        <td className={`${CELDA} min-w-56`}>
          <div className="flex items-center gap-2">
            {fila.ruta_recorte && (
              <Recorte
                src={p.api.urlRecorteFila(p.evaluacionId, fila.item)}
                alt={`Observación escrita a mano del ítem ${fila.item}`}
                clase="max-h-10 max-w-40 shrink-0"
              />
            )}
            <div className="min-w-0 grow">
              <textarea
                aria-label={`Observación del ítem ${fila.item}`}
                rows={1}
                value={observacion}
                onFocus={p.alElegir}
                onChange={(e) => p.alCambiarObservacion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    p.alConfirmar();
                  }
                }}
                className="w-full resize-none rounded-md border border-slate-300 px-2 py-1 text-base [field-sizing:content]"
              />
              {fila.texto_ocr && observacion === fila.texto_ocr && (
                <span className="block text-xs text-slate-600">(leída de la foto: puede tener errores)</span>
              )}
            </div>
          </div>
        </td>
      )}

      <td className={`${CELDA} pr-2 text-center`}>
        <button
          type="button"
          aria-label={`Confirmar fila ${fila.item}`}
          title={hecha ? "Fila revisada" : "Confirmar esta fila (Enter)"}
          disabled={p.guardando || hecha}
          onClick={(e) => {
            e.stopPropagation();
            p.alConfirmar();
          }}
          className={`mx-auto flex size-7 items-center justify-center rounded-md text-base font-bold disabled:cursor-default ${
            hecha ? "bg-emerald-100 text-emerald-700" : "bg-acento text-white hover:bg-acento-oscuro"
          }`}
        >
          ✓
        </button>
        <span className="sr-only">{cambiada ? "Con cambios" : fila.revisada ? "Revisada" : "Por revisar"}</span>
      </td>
    </tr>
  );
}

/** Filas seguidas con las mismas opciones comparten encabezado: una sola tabla por tramo. */
function tramosPorOpciones(
  filas: FilaGuardada[],
  info: Map<number, InfoItem>,
): { opciones: string[]; filas: FilaGuardada[] }[] {
  const tramos: { clave: string; opciones: string[]; filas: FilaGuardada[] }[] = [];
  for (const f of filas) {
    const opciones = info.get(f.item)?.opciones ?? [];
    const clave = opciones.join("\u0001");
    const ultimo = tramos[tramos.length - 1];
    if (ultimo && ultimo.clave === clave) ultimo.filas.push(f);
    else tramos.push({ clave, opciones, filas: [f] });
  }
  return tramos;
}

const ENCABEZADO =
  "sticky top-14 z-10 border-b-2 border-slate-300 bg-slate-100 px-1 py-1 text-center text-sm font-semibold";

function AvisoDeHoja({ pagina }: { pagina: PaginaGuardada }) {
  const sinCalzar = pagina.registro.ok === false;
  if (!sinCalzar && pagina.problemas_calidad.length === 0) return null;
  return (
    <div className="mb-2 space-y-1 px-3">
      {sinCalzar && (
        <Aviso>
          La foto no calzó bien con el formulario. Revisa que sea el formulario correcto y que la hoja se vea
          entera; si no, descártala y vuelve a sacarla.
        </Aviso>
      )}
      {pagina.problemas_calidad.length > 0 && (
        <Aviso tipo="info">Aviso de la foto: {pagina.problemas_calidad.join(" ")}</Aviso>
      )}
    </div>
  );
}

interface PropsRevision {
  api: Cliente;
  evaluacion: Evaluacion;
  plantilla: Plantilla;
  alActualizar: (ev: Evaluacion) => void;
  alDescartar: (pagina: number) => Promise<void>;
}

/** Pantalla de revisión (AP-R5): una tabla con la pregunta, las casillas, los avisos y la observación. */
export function Revision({ api, evaluacion, plantilla, alActualizar, alDescartar }: PropsRevision) {
  const info = useMemo(() => infoDeItems(plantilla), [plantilla]);
  const filas = evaluacion.filas;
  const [borradores, setBorradores] = useState<Record<number, Borrador>>({});
  const [activa, setActiva] = useState<number | null>(() => (filas.find((f) => !f.revisada) ?? filas[0])?.item ?? null);
  const [soloPendientes, setSoloPendientes] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cabeceraSinConfirmar, setCabeceraSinConfirmar] = useState(false);

  useEffect(() => {
    // una foto descartada se lleva sus filas: si la activa ya no existe, pasa a la primera por revisar
    if (activa !== null && !filas.some((f) => f.item === activa)) {
      setActiva((filas.find((f) => !f.revisada) ?? filas[0])?.item ?? null);
    }
  }, [filas, activa]);

  const visibles = useMemo(
    () => (soloPendientes ? filas.filter((f) => !f.revisada || borradores[f.item]) : filas),
    [filas, soloPendientes, borradores],
  );
  const conObservaciones = useMemo(() => hayObservaciones(plantilla, filas), [plantilla, filas]);

  const poner = useCallback((item: number, cambio: Borrador) => {
    setBorradores((b) => ({ ...b, [item]: { ...b[item], ...cambio } }));
  }, []);

  const guardar = useCallback(
    async (cambio: Parameters<Cliente["corregirEvaluacion"]>[1]) => {
      setGuardando(true);
      setError(null);
      try {
        const nueva = await api.corregirEvaluacion(evaluacion.id, cambio);
        alActualizar(nueva);
        return nueva;
      } catch (e) {
        setError(mensajeDe(e));
        return null;
      } finally {
        setGuardando(false);
      }
    },
    [api, evaluacion.id, alActualizar],
  );

  const confirmarFila = useCallback(
    async (item: number) => {
      const b = borradores[item] ?? {};
      const nueva = await guardar({
        filas: [{ item, ...("opcion" in b ? { opcion: b.opcion ?? null } : {}), observacion: b.observacion }],
      });
      if (!nueva) return;
      setBorradores(({ [item]: _, ...resto }) => resto);
      // sigue con la próxima fila por revisar después de esta; si no hay, con la siguiente a secas
      const orden = nueva.filas;
      const desde = orden.findIndex((f) => f.item === item);
      const siguiente =
        orden.slice(desde + 1).find((f) => !f.revisada) ??
        orden.find((f) => !f.revisada) ??
        orden[desde + 1] ??
        orden[desde];
      if (siguiente) setActiva(siguiente.item);
    },
    [borradores, guardar],
  );

  /** Confirma de una vez todas las filas por revisar (con lo que ya se haya cambiado en ellas). */
  const confirmarTodas = useCallback(async () => {
    const porConfirmar = filas.filter((f) => !f.revisada || borradores[f.item]);
    if (porConfirmar.length === 0) return;
    const conAvisos = porConfirmar.filter((f) => f.banderas.length > 0).length;
    const aviso =
      conAvisos > 0
        ? `${conAvisos} de ellas tienen avisos (marca dudosa, doble o sin marca). `
        : "";
    if (
      !window.confirm(
        `Vas a confirmar ${porConfirmar.length} fila(s) sin revisarlas una por una. ${aviso}¿Confirmar todas?`,
      )
    ) {
      return;
    }
    const nueva = await guardar({
      filas: porConfirmar.map((f) => {
        const b = borradores[f.item] ?? {};
        return { item: f.item, ...("opcion" in b ? { opcion: b.opcion ?? null } : {}), observacion: b.observacion };
      }),
    });
    if (nueva) setBorradores({});
  }, [filas, borradores, guardar]);

  // Teclado: ↑/↓ cambian de fila, 1–9 eligen la opción, 0 «sin respuesta», Enter confirma.
  const tecla = useRef<(e: KeyboardEvent) => void>(() => undefined);
  tecla.current = (e) => {
    const destino = e.target as HTMLElement | null;
    if (destino && ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "SUMMARY"].includes(destino.tagName)) return;
    if (e.ctrlKey || e.metaKey || e.altKey || activa === null || guardando) return;
    const pos = visibles.findIndex((f) => f.item === activa);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const otra = visibles[Math.min(visibles.length - 1, Math.max(0, pos + (e.key === "ArrowDown" ? 1 : -1)))];
      if (otra) setActiva(otra.item);
    } else if (/^[0-9]$/.test(e.key)) {
      const opciones = info.get(activa)?.opciones ?? [];
      if (e.key === "0") poner(activa, { opcion: null });
      else if (Number(e.key) <= opciones.length) poner(activa, { opcion: opciones[Number(e.key) - 1] });
      else return;
      e.preventDefault();
    } else if (e.key === "Enter") {
      e.preventDefault();
      void confirmarFila(activa);
    }
  };
  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => tecla.current(e);
    window.addEventListener("keydown", alPulsar);
    return () => window.removeEventListener("keydown", alPulsar);
  }, []);

  const pendientes = evaluacion.filas_pendientes;
  const campos = camposDeCabecera(plantilla, evaluacion);
  const porPagina = evaluacion.paginas.map((pg) => ({
    pagina: pg,
    tramos: tramosPorOpciones(
      visibles.filter((f) => f.pagina === pg.pagina),
      info,
    ),
  }));

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-20 flex h-14 flex-wrap items-center gap-x-5 gap-y-0 overflow-hidden rounded-lg border border-slate-200 bg-white/95 px-3 shadow-sm">
        <h2 className="truncate text-lg font-semibold">
          {evaluacion.paciente || "Paciente sin nombre"}
          <span className="ml-2 text-base font-normal text-slate-600">{plantilla.nombre}</span>
        </h2>
        <p role="status" className="text-base font-semibold">
          {textoFaltan(pendientes)}
          {pendientes === 0 && evaluacion.cabecera_revisada ? " · Lista para exportar" : ""}
        </p>
        <label className="flex items-center gap-2 text-base">
          <input
            type="checkbox"
            checked={soloPendientes}
            onChange={(e) => setSoloPendientes(e.target.checked)}
            className="size-5"
          />
          Mostrar solo lo que falta
        </label>
        <Boton
          variante="suave"
          className="px-3 py-1 text-sm"
          disabled={guardando || (pendientes === 0 && Object.keys(borradores).length === 0)}
          onClick={() => void confirmarTodas()}
        >
          Confirmar todas las filas
        </Boton>
        <p className="hidden text-sm text-slate-600 2xl:block">
          Teclado: ↑ ↓ fila · 1, 2, 3… respuesta · 0 sin respuesta · Enter confirma
        </p>
        <a className="ml-auto text-acento underline" href={enlace.evaluaciones}>
          Volver a la lista
        </a>
      </div>

      {error && <Aviso>{error}</Aviso>}

      <Cabecera
        key={`${evaluacion.id}-${evaluacion.paciente}-${JSON.stringify(evaluacion.cabecera)}`}
        api={api}
        evaluacion={evaluacion}
        campos={campos}
        guardando={guardando}
        alConfirmar={(paciente, cabecera) => void guardar({ paciente, cabecera })}
        alCambiarEstado={setCabeceraSinConfirmar}
      />

      {porPagina.map(({ pagina, tramos }) => (
        <section key={pagina.pagina} className="rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-3 px-3 py-1">
            <h3 className="text-base font-semibold">
              {evaluacion.paginas.length > 1 ? `Hoja ${pagina.pagina + 1}` : "Respuestas"}
            </h3>
            <Boton
              variante="suave"
              className="px-3 py-0.5 text-sm"
              disabled={guardando}
              onClick={() => {
                if (
                  window.confirm(
                    "¿Descartar esta foto? Se borra la foto y lo leído de ella, para que puedas volver a sacarla.",
                  )
                ) {
                  void alDescartar(pagina.pagina);
                }
              }}
            >
              Descartar esta foto
            </Boton>
          </div>
          <AvisoDeHoja pagina={pagina} />
          {tramos.length === 0 ? (
            <p className="px-3 pb-3 text-slate-600">No queda nada por revisar en esta hoja.</p>
          ) : (
            tramos.map((tramo, n) => (
              <table key={n} className="w-full border-collapse text-[0.95rem]">
                <thead>
                  <tr>
                    <th scope="col" className={`${ENCABEZADO} pl-2 text-left`}>
                      Pregunta
                    </th>
                    {tramo.opciones.map((o) => (
                      <th key={o} scope="col" className={`${ENCABEZADO} w-20 leading-tight`}>
                        {o}
                      </th>
                    ))}
                    <th scope="col" className={`${ENCABEZADO} w-14 leading-tight`}>
                      Sin resp.
                    </th>
                    <th scope="col" className={`${ENCABEZADO} w-16`}>
                      Avisos
                    </th>
                    {conObservaciones && (
                      <th scope="col" className={`${ENCABEZADO} w-[26%] text-left`}>
                        Observación
                      </th>
                    )}
                    <th scope="col" className={`${ENCABEZADO} w-14`}>
                      <span className="sr-only">Confirmar</span>✓
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {tramo.filas.map((f) => (
                    <FilaTabla
                      key={f.item}
                      api={api}
                      evaluacionId={evaluacion.id}
                      fila={f}
                      info={info.get(f.item)}
                      borrador={borradores[f.item]}
                      activa={activa === f.item}
                      guardando={guardando}
                      conObservaciones={conObservaciones}
                      alElegir={() => setActiva(f.item)}
                      alCambiarOpcion={(o) => poner(f.item, { opcion: o })}
                      alCambiarObservacion={(t) => poner(f.item, { observacion: t })}
                      alConfirmar={() => void confirmarFila(f.item)}
                    />
                  ))}
                </tbody>
              </table>
            ))
          )}
        </section>
      ))}

      <Exportar
        api={api}
        evaluacion={evaluacion}
        cambiosSinGuardar={cabeceraSinConfirmar || Object.keys(borradores).length > 0}
        alExportar={alActualizar}
      />
    </div>
  );
}

export function PantallaRevision({ id }: { id: string }) {
  const api = useApi();
  const carga = useCarga(async () => {
    const ev = await api.evaluacion(id);
    return { ev, plantilla: await api.plantilla(ev.plantilla_id, ev.plantilla_version) };
  });
  const [actual, setActual] = useState<Evaluacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setActual(null), [id]);
  const evaluacion = actual ?? carga.datos?.ev ?? null;

  const descartar = useCallback(
    async (pagina: number) => {
      try {
        const r = await api.descartarPagina(id, pagina);
        if (r.evaluacion_eliminada) window.location.hash = enlace.evaluaciones;
        else setActual(await api.evaluacion(id));
      } catch (e) {
        setError(mensajeDe(e));
      }
    },
    [api, id],
  );

  if (carga.error && !evaluacion) {
    return (
      <Tarjeta titulo="Revisión">
        <Aviso>{carga.error}</Aviso>
        <p className="mt-4">
          <a className="text-acento underline" href={enlace.evaluaciones}>
            Volver a la lista
          </a>
        </p>
      </Tarjeta>
    );
  }
  if (!evaluacion || !carga.datos) return <p className="text-slate-600">Cargando…</p>;
  return (
    <>
      {error && <Aviso>{error}</Aviso>}
      <Revision
        key={evaluacion.id}
        api={api}
        evaluacion={evaluacion}
        plantilla={carga.datos.plantilla}
        alActualizar={setActual}
        alDescartar={descartar}
      />
    </>
  );
}
