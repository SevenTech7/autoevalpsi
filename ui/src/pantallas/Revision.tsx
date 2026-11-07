import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Cliente } from "../api/cliente";
import type { Evaluacion, FilaGuardada, Plantilla } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
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

function Recorte({ src, alt }: { src: string; alt: string }) {
  const [roto, setRoto] = useState(false);
  if (roto) return <p className="text-sm text-slate-500">Sin imagen guardada.</p>;
  return (
    <img
      src={src}
      alt={alt}
      onError={() => setRoto(true)}
      className="max-h-24 max-w-full rounded border border-slate-200 bg-white object-contain"
    />
  );
}

interface PropsCabecera {
  api: Cliente;
  evaluacion: Evaluacion;
  campos: string[];
  guardando: boolean;
  alConfirmar: (paciente: string, cabecera: Record<string, string>) => void;
}

function Cabecera({ api, evaluacion, campos, guardando, alConfirmar }: PropsCabecera) {
  const [paciente, setPaciente] = useState(evaluacion.paciente);
  const [valores, setValores] = useState<Record<string, string>>(evaluacion.cabecera);
  const cambiada =
    paciente !== evaluacion.paciente || campos.some((c) => (valores[c] ?? "") !== (evaluacion.cabecera[c] ?? ""));

  const campo = (clave: string, etiqueta: string, valor: string, poner: (v: string) => void) => (
    <div key={clave} className="space-y-1">
      <label className="block text-base font-medium" htmlFor={`cab-${clave}`}>
        {etiqueta}
      </label>
      {evaluacion.recortes_cabecera[clave] && (
        <Recorte src={api.urlRecorteCabecera(evaluacion.id, clave)} alt={`Lo escrito en «${etiqueta}»`} />
      )}
      <input
        id={`cab-${clave}`}
        value={valor}
        onChange={(e) => poner(e.target.value)}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
      />
    </div>
  );

  return (
    <Tarjeta
      titulo="Datos de la hoja"
      acciones={
        evaluacion.cabecera_revisada && !cambiada ? (
          <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm text-emerald-900">Confirmados</span>
        ) : (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-900">Sin confirmar</span>
        )
      }
    >
      <p className="mb-3 text-slate-600">
        Fecha de la evaluación: {fechaLegible(evaluacion.fecha)}. Lo que se lee de la letra puede tener errores:
        compara con la imagen.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {campo("paciente", "Paciente", paciente, setPaciente)}
        {campos.map((c) => campo(c, c, valores[c] ?? "", (v) => setValores({ ...valores, [c]: v })))}
      </div>
      <div className="mt-4">
        <Boton
          disabled={guardando || (evaluacion.cabecera_revisada && !cambiada)}
          onClick={() => alConfirmar(paciente, Object.fromEntries(campos.map((c) => [c, valores[c] ?? ""])))}
        >
          Confirmar datos de la hoja
        </Boton>
      </div>
    </Tarjeta>
  );
}

interface PropsFila {
  api: Cliente;
  evaluacionId: string;
  fila: FilaGuardada;
  info: InfoItem | undefined;
  borrador: Borrador | undefined;
  activa: boolean;
  guardando: boolean;
  alElegir: () => void;
  alCambiarOpcion: (opcion: string | null) => void;
  alCambiarObservacion: (texto: string) => void;
  alConfirmar: () => void;
}

function FilaRevision(p: PropsFila) {
  const { fila, info, borrador, activa } = p;
  const opciones = info?.opciones ?? [];
  const opcion = borrador && "opcion" in borrador ? (borrador.opcion ?? null) : fila.opcion;
  const observacion = borrador?.observacion ?? fila.observacion;
  const cambiada = borrador !== undefined && Object.keys(borrador).length > 0;
  const ref = useRef<HTMLLIElement>(null);

  useEffect(() => {
    if (activa) ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [activa]);

  const color = fila.revisada && !cambiada ? "border-slate-200 bg-white" : "border-amber-300 bg-amber-50";
  return (
    <li
      ref={ref}
      aria-current={activa ? "true" : undefined}
      data-item={fila.item}
      onClick={p.alElegir}
      className={`rounded-xl border-2 p-4 ${color} ${activa ? "ring-2 ring-acento" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-lg font-semibold">
          {fila.item}. {info?.texto || `Ítem ${fila.item}`}
        </h3>
        <span
          className={`rounded-full px-3 py-1 text-sm ${
            fila.revisada && !cambiada ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-900"
          }`}
        >
          {cambiada ? "Con cambios" : fila.revisada ? "Revisada" : "Por revisar"}
        </span>
      </div>

      {fila.banderas.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2 text-sm text-amber-900">
          {fila.banderas.map((b) => (
            <li key={b} className="rounded bg-amber-100 px-2 py-0.5">
              {describirBandera(b)}
            </li>
          ))}
        </ul>
      )}

      <div role="radiogroup" aria-label={`Respuesta del ítem ${fila.item}`} className="mt-3 flex flex-wrap gap-2">
        {opciones.map((o, n) => (
          <button
            key={o}
            type="button"
            role="radio"
            aria-checked={opcion === o}
            onClick={() => {
              p.alElegir();
              p.alCambiarOpcion(o);
            }}
            className={`min-w-14 rounded-lg border px-4 py-2 text-base font-medium ${
              opcion === o ? "border-acento bg-acento text-white" : "border-slate-300 bg-white hover:bg-slate-50"
            }`}
          >
            <span className="mr-1 text-xs opacity-70">{n + 1}</span>
            {o}
          </button>
        ))}
        <button
          type="button"
          role="radio"
          aria-checked={opcion === null}
          onClick={() => {
            p.alElegir();
            p.alCambiarOpcion(null);
          }}
          className={`rounded-lg border px-4 py-2 text-base ${
            opcion === null ? "border-slate-700 bg-slate-700 text-white" : "border-slate-300 bg-white hover:bg-slate-50"
          }`}
        >
          <span className="mr-1 text-xs opacity-70">0</span>
          Sin respuesta
        </button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div>
          {fila.ruta_recorte ? (
            <Recorte
              src={p.api.urlRecorteFila(p.evaluacionId, fila.item)}
              alt={`Observación escrita a mano del ítem ${fila.item}`}
            />
          ) : (
            <p className="text-sm text-slate-500">No había nada escrito en la observación.</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium" htmlFor={`obs-${fila.item}`}>
            Observación del ítem {fila.item}
            {fila.texto_ocr && observacion === fila.texto_ocr && (
              <span className="ml-2 font-normal text-slate-600">(leída de la foto: puede tener errores)</span>
            )}
          </label>
          <textarea
            id={`obs-${fila.item}`}
            rows={2}
            value={observacion}
            onFocus={p.alElegir}
            onChange={(e) => p.alCambiarObservacion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                p.alConfirmar();
              }
            }}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
          />
        </div>
      </div>

      <div className="mt-3">
        <Boton disabled={p.guardando || (fila.revisada && !cambiada)} onClick={p.alConfirmar}>
          Confirmar fila {fila.item}
        </Boton>
      </div>
    </li>
  );
}

interface PropsRevision {
  api: Cliente;
  evaluacion: Evaluacion;
  plantilla: Plantilla;
  alActualizar: (ev: Evaluacion) => void;
  alDescartar: (pagina: number) => Promise<void>;
}

/** Pantalla de revisión (AP-R5): cada fila con su recorte, sus casillas y su observación editable. */
export function Revision({ api, evaluacion, plantilla, alActualizar, alDescartar }: PropsRevision) {
  const info = useMemo(() => infoDeItems(plantilla), [plantilla]);
  const filas = evaluacion.filas;
  const [borradores, setBorradores] = useState<Record<number, Borrador>>({});
  const [activa, setActiva] = useState<number | null>(() => (filas.find((f) => !f.revisada) ?? filas[0])?.item ?? null);
  const [soloPendientes, setSoloPendientes] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  // Teclado: ↑/↓ cambian de fila, 1–9 eligen la opción, 0 «sin respuesta», Enter confirma.
  const tecla = useRef<(e: KeyboardEvent) => void>(() => undefined);
  tecla.current = (e) => {
    const destino = e.target as HTMLElement | null;
    if (destino && ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(destino.tagName)) return;
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
    filas: visibles.filter((f) => f.pagina === pg.pagina),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">{evaluacion.paciente || "Paciente sin nombre"}</h2>
          <p className="text-slate-600">{plantilla.nombre}</p>
        </div>
        <a className="text-acento underline" href={enlace.evaluaciones}>
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
      />

      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white/95 px-4 py-3 shadow-sm">
        <p role="status" className="text-lg font-semibold">
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
        <p className="w-full text-sm text-slate-600">
          Teclado: ↑ ↓ cambian de fila · 1, 2, 3… eligen la respuesta · 0 es «sin respuesta» · Enter confirma.
        </p>
      </div>

      {porPagina.map(({ pagina, filas: deLaPagina }) => (
        <Tarjeta
          key={pagina.pagina}
          titulo={evaluacion.paginas.length > 1 ? `Hoja ${pagina.pagina + 1}` : "Respuestas"}
          acciones={
            <Boton
              variante="suave"
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
          }
        >
          {pagina.problemas_calidad.length > 0 && (
            <div className="mb-4">
              <Aviso tipo="info">Aviso de la foto: {pagina.problemas_calidad.join(" ")}</Aviso>
            </div>
          )}
          {deLaPagina.length === 0 ? (
            <p className="text-slate-600">No queda nada por revisar en esta hoja.</p>
          ) : (
            <ol className="space-y-3">
              {deLaPagina.map((f) => (
                <FilaRevision
                  key={f.item}
                  api={api}
                  evaluacionId={evaluacion.id}
                  fila={f}
                  info={info.get(f.item)}
                  borrador={borradores[f.item]}
                  activa={activa === f.item}
                  guardando={guardando}
                  alElegir={() => setActiva(f.item)}
                  alCambiarOpcion={(o) => poner(f.item, { opcion: o })}
                  alCambiarObservacion={(t) => poner(f.item, { observacion: t })}
                  alConfirmar={() => void confirmarFila(f.item)}
                />
              ))}
            </ol>
          )}
        </Tarjeta>
      ))}
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
