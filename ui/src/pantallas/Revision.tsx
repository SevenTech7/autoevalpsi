import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ErrorApi } from "../api/cliente";
import type { Cliente } from "../api/cliente";
import type { Evaluacion, FilaGuardada, PaginaGuardada, Plantilla } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { hayDialogoAbierto, useDialogos } from "../componentes/Dialogos";
import { Exportar, useExportar } from "../componentes/Exportar";
import { fechaHoraBolivia } from "../componentes/TablaEvaluaciones";
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
  celda_vacia: "La celda está vacía",
  ocr_digito_dudoso: "El número se lee dudoso",
  ocr_digito_ilegible: "No se pudo leer el número",
  ocr_sin_lector: "No se pudo leer el número: el lector de texto no está activo",
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
  tipo: "marcas" | "digito";
  seccion: string | null;
}

/** El número impreso en la hoja: «ESCUCHAR Y ENTENDER · 31» → «31» (el `item` es solo interno). */
function numeroImpreso(texto: string | undefined, item: number): string {
  const n = texto?.split(" · ").pop()?.trim();
  return n && /^[0-9]+$/.test(n) ? n : String(item);
}

function infoDeItems(plantilla: Plantilla): Map<number, InfoItem> {
  const mapa = new Map<number, InfoItem>();
  for (const p of plantilla.paginas) {
    for (const t of p.tablas) {
      for (const f of t.filas) {
        mapa.set(f.item, {
          texto: f.texto,
          opciones: t.opciones,
          tipo: t.tipo ?? "marcas",
          seccion: t.seccion ?? null,
        });
      }
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
  // el recorte de una celda de número no es una observación: tiene su propia columna
  const digitos = new Set(
    plantilla.paginas.flatMap((p) =>
      p.tablas.filter((t) => t.tipo === "digito").flatMap((t) => t.filas.map((f) => f.item)),
    ),
  );
  return (
    declarada ||
    filas.some((f) => !digitos.has(f.item) && (f.ruta_recorte || f.texto_ocr || f.observacion))
  );
}

// --- iconos de aviso -----------------------------------------------------------------------------

type Dibujo = { color: string; trazo: ReactNode };

const DIBUJOS: Record<string, Dibujo> = {
  // círculo punteado: no hay marca
  sin_marca: {
    color: "text-slate-600",
    trazo: <circle cx="12" cy="12" r="8" strokeDasharray="3 3" />,
  },
  // el mismo círculo punteado: celda de número vacía
  celda_vacia: {
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
  useEffect(() => alCambiarEstado(cambiada), [cambiada, alCambiarEstado]);
  useEffect(() => () => alCambiarEstado(false), [alCambiarEstado]); // al desmontarse
  const confirmada = evaluacion.cabecera_revisada && !cambiada;
  // Abierta al entrar si falta confirmarla. Después solo la abre o la cierra la usuaria: lo que
  // escriba no debe plegarla ni desplegarla (antes `open` seguía a «confirmada» y se cerraba sola
  // en mitad de la edición cuando lo escrito volvía a ser igual a lo leído).
  const [abierta, setAbierta] = useState(!evaluacion.cabecera_revisada);

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
    <details
      open={abierta}
      onToggle={(e) => setAbierta(e.currentTarget.open)}
      className="rounded-lg border border-slate-200 bg-white shadow-sm"
    >
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
          Registrada el {fechaHoraBolivia(evaluacion.creada_en)} (hora de Bolivia) · lo leído de la letra puede tener errores
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

/** Pedido de llevar una fila a la vista; `n` distingue pedidos repetidos de la misma fila. */
interface Ver {
  item: number;
  centrar: boolean;
  n: number;
}

interface PropsFila {
  api: Cliente;
  evaluacionId: string;
  fila: FilaGuardada;
  info: InfoItem | undefined;
  borrador: Borrador | undefined;
  activa: boolean;
  ver: Ver | null;
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
  const digitos = info?.tipo === "digito";
  const opcion = borrador && "opcion" in borrador ? (borrador.opcion ?? null) : fila.opcion;
  const observacion = borrador?.observacion ?? fila.observacion;
  const cambiada = borrador !== undefined && Object.keys(borrador).length > 0;
  const ref = useRef<HTMLTableRowElement>(null);

  // Solo se desplaza cuando la usuaria lo pidió (flechas, «siguiente», «ir a la primera»): elegir una
  // hoja o hacer clic en una fila no debe mover la página.
  useEffect(() => {
    if (p.ver) ref.current?.scrollIntoView?.({ block: p.ver.centrar ? "center" : "nearest" });
  }, [p.ver]);

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
      className={`scroll-mt-36 scroll-mb-4 ${fondo} ${activa ? "outline outline-2 -outline-offset-2 outline-acento" : ""}`}
    >
      {digitos ? (
        <th scope="row" className={`${CELDA} pl-2 pr-3 text-left`} title={info?.texto}>
          <span className="inline-block min-w-8 text-lg font-semibold">
            {numeroImpreso(info?.texto, fila.item)}
          </span>
        </th>
      ) : (
        <th scope="row" className={`${CELDA} pl-2 pr-3 text-left font-normal`}>
          <span className="mr-2 inline-block min-w-6 font-semibold text-slate-500">{fila.item}.</span>
          <span title={info?.texto}>{info?.texto || `Ítem ${fila.item}`}</span>
        </th>
      )}

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
              title={`${digitos ? o : `${n + 1} · ${o}`}${leida ? " (lo que leyó la aplicación)" : ""}`}
              onClick={() => elegir(o)}
              className={`mx-auto flex size-7 items-center justify-center rounded-full border-2 text-sm font-semibold ${
                elegida
                  ? "border-acento bg-acento text-white"
                  : leida
                    ? "border-dashed border-slate-400 bg-white text-slate-400"
                    : "border-slate-300 bg-white text-transparent hover:border-acento hover:text-slate-300"
              }`}
            >
              {elegida ? "✓" : digitos ? o : n + 1}
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
          title={digitos ? "Borrar · Sin respuesta" : "0 · Sin respuesta"}
          onClick={() => elegir(null)}
          className={`mx-auto flex h-7 min-w-7 items-center justify-center rounded-full border-2 px-1 text-sm ${
            opcion === null
              ? "border-slate-700 bg-slate-700 text-white"
              : "border-slate-300 bg-white text-slate-400 hover:border-slate-500"
          }`}
        >
          {opcion === null || digitos ? "—" : "0"}
        </button>
      </td>

      <td className={`${CELDA} text-center`}>
        <span className="inline-flex items-center justify-center gap-0.5">
          {fila.banderas.map((b) => (
            <IconoAviso key={b} bandera={b} />
          ))}
        </span>
      </td>

      {digitos && (
        <td className={`${CELDA} w-28 text-center`}>
          {fila.ruta_recorte ? (
            <div className="flex h-10 items-center justify-center">
              <Recorte
                src={p.api.urlRecorteFila(p.evaluacionId, fila.item)}
                alt={`Lo escrito en el ítem ${fila.item}`}
                clase="mx-auto max-h-10 max-w-24"
              />
            </div>
          ) : (
            <span className="text-sm text-slate-500">vacía</span>
          )}
        </td>
      )}

      {!digitos && p.conObservaciones && (
        <td className={`${CELDA} min-w-56`}>
          <div className="flex items-center gap-2">
            {fila.ruta_recorte && (
              <div className="flex h-10 w-40 shrink-0 items-center">
                <Recorte
                  src={p.api.urlRecorteFila(p.evaluacionId, fila.item)}
                  alt={`Observación escrita a mano del ítem ${fila.item}`}
                  clase="max-h-10 max-w-40"
                />
              </div>
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
): { opciones: string[]; filas: FilaGuardada[]; titulo: string | null }[] {
  const tramos: { clave: string; opciones: string[]; filas: FilaGuardada[]; titulo: string | null }[] = [];
  for (const f of filas) {
    const opciones = info.get(f.item)?.opciones ?? [];
    const tipo = info.get(f.item)?.tipo ?? "marcas";
    // En un formulario de números cada área (columna maestra) es una sola lista Número · Valor,
    // aunque la hoja la parta en dos columnas (1–30 y 31–39) o en varias tablas.
    const titulo = tipo === "digito" ? (info.get(f.item)?.seccion ?? null) : null;
    const clave = `${tipo}\u0002${opciones.join("\u0001")}\u0002${titulo ?? ""}`;
    const ultimo = tramos[tramos.length - 1];
    if (ultimo && ultimo.clave === clave) ultimo.filas.push(f);
    else tramos.push({ clave, opciones, filas: [f], titulo });
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

/** Menú «⋯» de la barra: lo que no se usa a cada rato (atajos y eliminar). Se cierra con Esc o al
 * hacer clic fuera. */
function MenuMas({ children }: { children: ReactNode }) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => {
      if (caja.current && !caja.current.contains(e.target as Node)) setAbierto(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setAbierto(false);
    document.addEventListener("mousedown", fuera);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fuera);
      document.removeEventListener("keydown", esc);
    };
  }, [abierto]);
  return (
    <div ref={caja} className="relative shrink-0">
      <Boton
        variante="suave"
        className="px-3 py-1 text-base"
        aria-label="Más acciones"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto(!abierto)}
      >
        ⋯
      </Boton>
      {abierto && (
        <div
          role="menu"
          className="absolute right-0 top-full z-30 mt-1 w-80 space-y-2 rounded-lg border border-slate-200 bg-white p-3 shadow-lg"
          onClick={() => setAbierto(false)}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/** Una pestaña por hoja del formulario: dice si ya está subida y cuántas filas le faltan. */
function PestanasHojas({
  total,
  evaluacion,
  activa,
  alElegir,
}: {
  total: number;
  evaluacion: Evaluacion;
  activa: number;
  alElegir: (hoja: number) => void;
}) {
  const subidas = new Set(evaluacion.paginas.map((p) => p.pagina));
  return (
    <div role="tablist" aria-label="Hojas de la evaluación" className="flex flex-wrap gap-2">
      {Array.from({ length: total }, (_, n) => {
        const falta = !subidas.has(n);
        const porRevisar = evaluacion.filas.filter((f) => f.pagina === n && !f.revisada).length;
        const elegida = activa === n;
        return (
          <button
            key={n}
            type="button"
            role="tab"
            id={`hoja-${n}`}
            aria-selected={elegida}
            aria-controls="hoja-contenido"
            onClick={() => alElegir(n)}
            className={`rounded-lg border px-4 py-1.5 text-base font-medium ${
              elegida ? "border-acento bg-white shadow-sm" : "border-slate-300 bg-slate-100 hover:bg-white"
            }`}
          >
            Hoja {n + 1}
            {falta ? (
              <span className="ml-2 text-amber-800">· falta</span>
            ) : porRevisar > 0 ? (
              <span className="ml-2 text-amber-800">· {porRevisar} por revisar</span>
            ) : (
              <span className="ml-2 text-emerald-800">✓</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Lo que se ve en la pestaña de una hoja que todavía no tiene foto: dónde subirla. */
function HojaFaltante({ n, alSubir }: { n: number; alSubir?: (pagina: number, foto: File) => Promise<void> }) {
  const [subiendo, setSubiendo] = useState(false);
  async function subir(foto: File) {
    if (!alSubir) return;
    setSubiendo(true);
    try {
      await alSubir(n, foto);
    } finally {
      setSubiendo(false);
    }
  }
  return (
    <div className="space-y-2 px-3 py-3">
      <p className="text-amber-900">
        <strong>Falta la foto de la hoja {n + 1}.</strong>
      </p>
      {alSubir && (
        <label className="inline-block cursor-pointer rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-base font-medium hover:bg-slate-50">
          {subiendo ? "Subiendo y leyendo…" : `Subir la foto de la hoja ${n + 1}`}
          <input
            type="file"
            accept="image/jpeg,image/png"
            aria-label={`Subir la foto de la hoja ${n + 1}`}
            disabled={subiendo}
            className="sr-only"
            onChange={(e) => {
              const foto = e.target.files?.[0];
              e.target.value = "";
              if (foto) void subir(foto);
            }}
          />
        </label>
      )}
      <p className="text-sm text-slate-700">
        También puedes tomarla con el celular: ábrelo y elige esta evaluación en «¿Seguir una evaluación a la que le falta
        una hoja?».
      </p>
    </div>
  );
}

interface PropsRevision {
  api: Cliente;
  evaluacion: Evaluacion;
  plantilla: Plantilla;
  alActualizar: (ev: Evaluacion) => void;
  alDescartar: (pagina: number) => Promise<void>;
  alEliminar?: () => Promise<void>; // elimina la evaluación entera
  alSubirHoja?: (pagina: number, foto: File) => Promise<void>; // sube la foto de una hoja que falta
}

/** Pantalla de revisión (AP-R5): una tabla con la pregunta, las casillas, los avisos y la observación. */
export function Revision({
  api,
  evaluacion,
  plantilla,
  alActualizar,
  alDescartar,
  alEliminar,
  alSubirHoja,
}: PropsRevision) {
  const info = useMemo(() => infoDeItems(plantilla), [plantilla]);
  const filas = evaluacion.filas;
  const [borradores, setBorradores] = useState<Record<number, Borrador>>({});
  const [activa, setActiva] = useState<number | null>(() => (filas.find((f) => !f.revisada) ?? filas[0])?.item ?? null);
  const [soloPendientes, setSoloPendientes] = useState(false);
  const total = plantilla.paginas.length;
  const [hoja, setHoja] = useState<number>(() => (filas.find((f) => !f.revisada) ?? filas[0])?.pagina ?? 0);
  const [ver, setVer] = useState<Ver | null>(null);
  const pedidos = useRef(0);
  const verFila = useCallback((item: number, centrar: boolean) => setVer({ item, centrar, n: ++pedidos.current }), []);
  const [guardando, setGuardando] = useState(false);
  const { avisar, confirmar } = useDialogos();
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
  const visiblesHoja = useMemo(() => visibles.filter((f) => f.pagina === hoja), [visibles, hoja]);
  const conObservaciones = useMemo(() => hayObservaciones(plantilla, filas), [plantilla, filas]);

  /** Cambiar de pestaña no mueve la página ni un píxel: la vista queda donde estaba. La fila activa
   * pasa a la primera por revisar, sin desplazar nada: para ir a ella está el botón «Ir a la
   * primera fila por revisar». */
  const irAHoja = useCallback(
    (n: number) => {
      setHoja(n);
      setVer(null);
      const aqui = filas.filter((f) => f.pagina === n);
      const primera = aqui.find((f) => !f.revisada) ?? aqui[0];
      if (primera) setActiva(primera.item);
    },
    [filas],
  );

  const poner = useCallback((item: number, cambio: Borrador) => {
    setBorradores((b) => ({ ...b, [item]: { ...b[item], ...cambio } }));
  }, []);

  const guardar = useCallback(
    async (cambio: Parameters<Cliente["corregirEvaluacion"]>[1]) => {
      setGuardando(true);
      try {
        const nueva = await api.corregirEvaluacion(evaluacion.id, cambio);
        alActualizar(nueva);
        return nueva;
      } catch (e) {
        void avisar({ tipo: "error", titulo: "No se pudo guardar", mensaje: mensajeDe(e) });
        return null;
      } finally {
        setGuardando(false);
      }
    },
    [api, evaluacion.id, alActualizar, avisar],
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
      if (siguiente) {
        setActiva(siguiente.item);
        setHoja(siguiente.pagina);
        // la contigua se muestra con el mínimo movimiento; una lejana, al centro
        verFila(siguiente.item, siguiente !== orden[desde + 1]);
      }
    },
    [borradores, guardar, verFila],
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
      !(await confirmar({
        titulo: "Confirmar todas las filas",
        mensaje: `Vas a confirmar ${porConfirmar.length} fila(s) sin revisarlas una por una. ${aviso}¿Confirmar todas?`,
        confirmar: "Sí, confirmar todas",
      }))
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
  }, [filas, borradores, guardar, confirmar]);

  // Teclado: ↑/↓ cambian de fila, 1–9 eligen la opción, 0 «sin respuesta», Enter confirma.
  const tecla = useRef<(e: KeyboardEvent) => void>(() => undefined);
  tecla.current = (e) => {
    const destino = e.target as HTMLElement | null;
    if (destino && ["INPUT", "TEXTAREA", "SELECT", "BUTTON", "SUMMARY"].includes(destino.tagName)) return;
    if (e.ctrlKey || e.metaKey || e.altKey || activa === null || guardando || hayDialogoAbierto()) return;
    const pos = visiblesHoja.findIndex((f) => f.item === activa);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const otra = visiblesHoja[Math.min(visiblesHoja.length - 1, Math.max(0, pos + (e.key === "ArrowDown" ? 1 : -1)))];
      if (otra) {
        setActiva(otra.item);
        verFila(otra.item, false);
      }
    } else if (info.get(activa)?.tipo === "digito" && (/^[0-9]$/.test(e.key) || e.key === "Backspace" || e.key === "Delete")) {
      // en una tabla de números, la tecla es el número mismo; Borrar deja la celda sin respuesta
      const opciones = info.get(activa)?.opciones ?? [];
      if (e.key === "Backspace" || e.key === "Delete") poner(activa, { opcion: null });
      else if (opciones.includes(e.key)) poner(activa, { opcion: e.key });
      else return;
      e.preventDefault();
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
  const revisadas = filas.filter((f) => f.revisada).length;
  const paginaActual = evaluacion.paginas.find((pg) => pg.pagina === hoja);
  const tramos = paginaActual ? tramosPorOpciones(visiblesHoja, info) : [];
  const varias = total > 1;
  const primeraPendiente = filas.find((f) => f.pagina === hoja && (!f.revisada || borradores[f.item]));
  const irAPrimeraPendiente = () => {
    // si en esta hoja no queda nada, busca la primera de cualquier hoja
    const f = primeraPendiente ?? filas.find((x) => !x.revisada);
    if (!f) return;
    setHoja(f.pagina);
    setActiva(f.item);
    verFila(f.item, true);
  };
  const exportar = useExportar({
    api,
    evaluacion,
    cambiosSinGuardar: cabeceraSinConfirmar || Object.keys(borradores).length > 0,
    alExportar: alActualizar,
  });

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-20 space-y-2 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 shadow-sm">
        <div className="flex items-center gap-x-4">
          <a className="shrink-0 whitespace-nowrap text-acento underline" href={enlace.evaluaciones}>
            ← Lista
          </a>
          <h2 className="min-w-0 shrink truncate text-lg font-semibold">
            {evaluacion.paciente || "Paciente sin nombre"}
            <span className="ml-2 text-base font-normal text-slate-600">{plantilla.nombre}</span>
          </h2>
          <p
            role="status"
            className={`shrink-0 whitespace-nowrap rounded-full px-3 py-0.5 text-base font-semibold ${
              pendientes === 0 && evaluacion.cabecera_revisada ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-900"
            }`}
          >
            {textoFaltan(pendientes)}
            {pendientes === 0 && evaluacion.cabecera_revisada ? " · Lista para exportar" : ""}
          </p>
          <div className="ml-auto flex shrink-0 flex-col items-end">
            <Boton
              className={`whitespace-nowrap px-4 py-1.5 ${exportar.bloqueo ? "cursor-not-allowed opacity-60" : ""}`}
              disabled={exportar.ocupado}
              aria-disabled={exportar.bloqueo !== null}
              aria-describedby={exportar.bloqueo ? "motivo-exportar" : undefined}
              onClick={() => {
                if (!exportar.bloqueo) return void exportar.exportar();
                // Sin respuesta muda: se explica en una ventana y se ofrece ir a lo que falta.
                void avisar({
                  tipo: "info",
                  titulo: "Todavía no se puede exportar",
                  mensaje: `${exportar.bloqueo} Cuando esté todo revisado y confirmado, el botón se activa.`,
                  accion:
                    pendientes > 0
                      ? { texto: "Ir a la primera fila por revisar", alHacer: irAPrimeraPendiente }
                      : { texto: "Ir a los datos de la hoja", alHacer: () => window.scrollTo({ top: 0 }) },
                });
              }}
            >
              {exportar.textoBoton}
            </Boton>
            {exportar.bloqueo && (
              <span id="motivo-exportar" className="mt-0.5 text-xs text-amber-900">
                No se puede exportar: {exportar.bloqueo.replace(/\.$/, "").replace(/^./, (c) => c.toLowerCase())}
              </span>
            )}
          </div>
          <MenuMas>
            <p className="text-sm font-semibold text-slate-700">Atajos de teclado</p>
            <p className="text-sm text-slate-600">↑ ↓ cambian de fila · 1, 2, 3… eligen la respuesta · 0 sin respuesta · Enter confirma</p>
            {alEliminar && (
              <Boton
                variante="suave"
                role="menuitem"
                className="w-full border-red-300 px-3 py-1 text-sm text-red-800"
                disabled={guardando}
                onClick={() => {
                  void confirmar({
                    titulo: "Eliminar la evaluación",
                    mensaje:
                      "Se elimina esta evaluación con sus fotos y lo leído. " +
                      "Los Excel que ya exportaste no se tocan. No se puede deshacer.",
                    confirmar: "Sí, eliminar",
                    peligro: true,
                  }).then((acepto) => {
                    if (acepto) void alEliminar();
                  });
                }}
              >
                Eliminar evaluación
              </Boton>
            )}
          </MenuMas>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <div
            role="progressbar"
            aria-label="Filas revisadas"
            aria-valuemin={0}
            aria-valuemax={filas.length}
            aria-valuenow={revisadas}
            className="h-2.5 w-48 overflow-hidden rounded-full bg-slate-200"
          >
            <div
              className="h-full bg-emerald-600"
              style={{ width: `${filas.length ? Math.round((revisadas / filas.length) * 100) : 0}%` }}
            />
          </div>
          <span className="text-sm text-slate-700">
            {revisadas} de {filas.length} revisadas
          </span>
          <label className="ml-auto flex shrink-0 items-center gap-2 whitespace-nowrap text-base">
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
            className="shrink-0 whitespace-nowrap px-3 py-1 text-sm"
            disabled={guardando || (pendientes === 0 && Object.keys(borradores).length === 0)}
            onClick={() => void confirmarTodas()}
          >
            Confirmar todas las filas
          </Boton>
        </div>
      </div>

      <Cabecera
        key={`${evaluacion.id}-${evaluacion.cabecera_revisada}-${evaluacion.paciente}-${JSON.stringify(evaluacion.cabecera)}`}
        api={api}
        evaluacion={evaluacion}
        campos={campos}
        guardando={guardando}
        alConfirmar={(paciente, cabecera) => void guardar({ paciente, cabecera })}
        alCambiarEstado={setCabeceraSinConfirmar}
      />

      {varias && <PestanasHojas total={total} evaluacion={evaluacion} activa={hoja} alElegir={irAHoja} />}

      <section
        id="hoja-contenido"
        role={varias ? "tabpanel" : undefined}
        aria-labelledby={varias ? `hoja-${hoja}` : undefined}
        className="scroll-mt-36 rounded-lg border border-slate-200 bg-white shadow-sm"
      >
        {!paginaActual ? (
          <HojaFaltante n={hoja} alSubir={alSubirHoja} />
        ) : (
          <>
            <div className="flex items-center justify-between gap-3 px-3 py-1">
              <h3 className="text-base font-semibold">{varias ? `Hoja ${paginaActual.pagina + 1}` : "Respuestas"}</h3>
              {primeraPendiente && (
                <Boton variante="suave" className="ml-auto px-3 py-0.5 text-sm" onClick={irAPrimeraPendiente}>
                  Ir a la primera fila por revisar
                </Boton>
              )}
              <Boton
                variante="suave"
                className="px-3 py-0.5 text-sm"
                disabled={guardando}
                onClick={() => {
                  void confirmar({
                    titulo: "Descartar esta foto",
                    mensaje: "Se borra la foto y lo leído de ella, para que puedas volver a sacarla.",
                    confirmar: "Sí, descartar",
                    peligro: true,
                  }).then((acepto) => {
                    if (acepto) void alDescartar(paginaActual.pagina);
                  });
                }}
              >
                Descartar esta foto
              </Boton>
            </div>
            <AvisoDeHoja pagina={paginaActual} />
            {tramos.length === 0 ? (
              <p className="px-3 pb-3 text-slate-600">No queda nada por revisar en esta hoja.</p>
            ) : (
              tramos.map((tramo) => (
                <table key={tramo.filas[0]!.item} className="w-full border-collapse text-[0.95rem]">
                {tramo.titulo && (
                  <caption className="bg-slate-200 px-2 py-1 text-left text-base font-semibold">
                    {tramo.titulo}
                  </caption>
                )}
                <thead>
                  <tr>
                    <th scope="col" className={`${ENCABEZADO} pl-2 text-left`}>
                      {info.get(tramo.filas[0]!.item)?.tipo === "digito" ? "Número" : "Pregunta"}
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
                    {info.get(tramo.filas[0]!.item)?.tipo === "digito" && (
                      <th scope="col" className={`${ENCABEZADO} w-28`}>
                        Lo escrito
                      </th>
                    )}
                    {info.get(tramo.filas[0]!.item)?.tipo !== "digito" && conObservaciones && (
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
                      ver={ver?.item === f.item ? ver : null}
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
          </>
        )}
      </section>

      <Exportar
        api={api}
        evaluacion={evaluacion}
        cambiosSinGuardar={cabeceraSinConfirmar || Object.keys(borradores).length > 0}
        alExportar={alActualizar}
        control={exportar}
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
  const { avisar } = useDialogos();

  useEffect(() => setActual(null), [id]);
  const evaluacion = actual ?? carga.datos?.ev ?? null;

  const descartar = useCallback(
    async (pagina: number) => {
      try {
        const r = await api.descartarPagina(id, pagina);
        if (r.evaluacion_eliminada) window.location.hash = enlace.evaluaciones;
        else setActual(await api.evaluacion(id));
      } catch (e) {
        void avisar({ tipo: "error", titulo: "No se pudo descartar", mensaje: mensajeDe(e) });
      }
    },
    [api, id, avisar],
  );

  const eliminar = useCallback(async () => {
    try {
      await api.eliminarEvaluacion(id);
      window.location.hash = enlace.evaluaciones;
    } catch (e) {
      void avisar({ tipo: "error", titulo: "No se pudo eliminar", mensaje: mensajeDe(e) });
    }
  }, [api, id, avisar]);

  const subirHoja = useCallback(
    async (pagina: number, foto: File) => {
      if (!evaluacion) return;
      try {
        const r = await api.subirFoto(id, evaluacion.plantilla_id, pagina, foto);
        if (r.repetir) {
          await avisar({
            tipo: "info",
            titulo: "Mejor repite la foto",
            mensaje: r.problemas_calidad.join(" "),
          });
        }
        for (let i = 0; i < 120; i++) {
          const cola = await api.cola();
          const t = cola.trabajos?.find((x) => x.id === r.trabajo.id);
          if (t?.estado === "error") {
            throw new ErrorApi(422, "lectura", t.mensaje || "No se pudo leer la foto.");
          }
          if (t?.estado === "lista") break;
          await new Promise((ok) => setTimeout(ok, 1500));
        }
        setActual(await api.evaluacion(id));
      } catch (e) {
        void avisar({ tipo: "error", titulo: "No se pudo subir la hoja", mensaje: mensajeDe(e) });
      }
    },
    [api, id, evaluacion, avisar],
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
      <Revision
        key={evaluacion.id}
        api={api}
        evaluacion={evaluacion}
        plantilla={carga.datos.plantilla}
        alActualizar={setActual}
        alDescartar={descartar}
        alEliminar={eliminar}
        alSubirHoja={subirHoja}
      />
    </>
  );
}
