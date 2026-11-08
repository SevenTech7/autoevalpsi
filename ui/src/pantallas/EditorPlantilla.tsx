import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type PointerEvent } from "react";

import type { Cliente } from "../api/cliente";
import type { Caja, PaginaDef, PlantillaDef } from "../api/tipos";
import { Aviso, Boton } from "../componentes/base";
import { hayDialogoAbierto, useDialogos } from "../componentes/Dialogos";
import { estadoInicial, reducirEditor } from "../editor/historial";
import {
  agregarCampoCabecera,
  agregarColumna,
  agregarFila,
  agregarPreguntaSiNo,
  celdaDeFila,
  celdaDelPaciente,
  rangosAVaciar,
  cajaDeCelda,
  contarItems,
  moverCabecera,
  moverCelda,
  quitarCampoCabecera,
  quitarColumna,
  quitarFila,
  quitarTabla,
  redimensionarCabecera,
  redimensionarCelda,
  renombrarCampoCabecera,
  renombrarOpcion,
  seccionDeTabla,
  seleccionValida,
  textoDeFila,
  type Borde,
  type Seleccion,
} from "../editor/modelo";
import { mensajeDe, useApi, useCarga } from "../hooks";
import { enlace } from "../ruta";

const COLORES = ["#2563eb", "#059669", "#d97706", "#7c3aed", "#db2777", "#0891b2", "#65a30d", "#dc2626"];
const conPagina = (def: PlantillaDef, i: number, pagina: PaginaDef): PlantillaDef => ({
  ...def,
  paginas: def.paginas.map((p, k) => (k === i ? pagina : p)),
});

type Esquina = "nw" | "ne" | "sw" | "se";
interface Arrastre {
  modo: "mover" | Esquina;
  x: number;
  y: number;
  base: PlantillaDef;
  sel: NonNullable<Seleccion>;
  movido: boolean;
}

function cajaDe(p: PaginaDef, s: NonNullable<Seleccion>): Caja {
  return s.tipo === "celda" ? cajaDeCelda(p, s.tabla, s.fila, s.columna) : p.cabecera[s.campo]!.caja;
}

function esCampoDeTexto(el: EventTarget | null): boolean {
  return el instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

export function EditorPlantilla({ id }: { id: string }) {
  const api = useApi();
  const carga = useCarga(() => api.plantillaDef(id));
  if (carga.error && !carga.datos) {
    return (
      <div className="space-y-4">
        <Aviso>{carga.error}</Aviso>
        <a href={enlace.plantillas} className="text-acento underline">
          Volver a las plantillas
        </a>
      </div>
    );
  }
  if (!carga.datos) return <p>Cargando la plantilla…</p>;
  return (
    <EditorCargado
      key={`${carga.datos.id}-${carga.datos.version}`}
      api={api}
      inicial={carga.datos}
      alGuardar={carga.recargar}
    />
  );
}

function EditorCargado({
  api,
  inicial,
  alGuardar,
}: {
  api: Cliente;
  inicial: PlantillaDef;
  alGuardar: () => void;
}) {
  const { avisar, confirmar } = useDialogos();
  const [estado, despachar] = useReducer(reducirEditor, inicial, estadoInicial);
  const { borrador } = estado;
  const [indicePagina, setIndicePagina] = useState(0);
  const [sel, setSel] = useState<Seleccion>(null);
  const [zoom, setZoom] = useState(0.5);
  const [guardando, setGuardando] = useState(false);
  const [listo, setListo] = useState(false);
  const [campoNuevo, setCampoNuevo] = useState("");
  const [ocupadoServidor, setOcupadoServidor] = useState(false);
  const entradaLibro = useRef<HTMLInputElement>(null);
  const entradaPagina = useRef<HTMLInputElement>(null);
  const contenedor = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const arrastre = useRef<Arrastre | null>(null);

  const pagina = borrador.paginas[indicePagina]!;
  const [ancho, alto] = pagina.tamano_px;
  const sinGuardar = useMemo(() => JSON.stringify(borrador) !== JSON.stringify(inicial), [borrador, inicial]);
  const seleccion = seleccionValida(pagina, sel);
  const panel = useRef<HTMLElement>(null);
  const idSeleccion = seleccion
    ? seleccion.tipo === "celda"
      ? `c${seleccion.tabla}-${seleccion.fila}`
      : `h${seleccion.campo}`
    : "";
  // Al elegir otra casilla, el panel vuelve arriba para mostrar sus propiedades
  useEffect(() => {
    if (idSeleccion && panel.current) panel.current.scrollTop = 0;
  }, [idSeleccion]);

  // Ajustar al ancho al abrir
  useEffect(() => {
    const w = contenedor.current?.clientWidth ?? 0;
    if (w > 0) setZoom(Math.min(1, Math.max(0.1, (w - 4) / ancho)));
  }, [ancho]);

  // Borrador guardado en este equipo: si la ventana se cerró sin guardar, se ofrece recuperarlo
  const claveBorrador = `autoevalpsi.borrador.${inicial.id}.${inicial.version}`;
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const guardado = window.localStorage.getItem(claveBorrador);
        if (guardado && guardado !== JSON.stringify(inicial)) {
          const si = await confirmar({
            titulo: "Cambios sin guardar",
            mensaje: "La última vez quedaron cambios sin guardar en esta plantilla. ¿Quieres recuperarlos?",
            confirmar: "Sí, recuperarlos",
            cancelar: "No, empezar de nuevo",
          });
          if (!vivo) return;
          if (si) despachar({ t: "aplicar", nuevo: JSON.parse(guardado) as PlantillaDef });
          else window.localStorage.removeItem(claveBorrador);
        }
      } catch {
        // sin almacenamiento o dato dañado: se sigue sin borrador
      }
      if (vivo) setListo(true);
    })();
    return () => {
      vivo = false;
    };
    // solo al abrir
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!listo) return;
    try {
      if (sinGuardar) window.localStorage.setItem(claveBorrador, JSON.stringify(borrador));
      else window.localStorage.removeItem(claveBorrador);
    } catch {
      // sin almacenamiento: no se guarda el borrador local
    }
  }, [borrador, sinGuardar, listo, claveBorrador]);

  const aplicar = useCallback((nuevo: PlantillaDef, clave?: string) => despachar({ t: "aplicar", nuevo, clave }), []);
  const aplicarPagina = (p: PaginaDef | null, clave?: string) => {
    if (p) aplicar(conPagina(borrador, indicePagina, p), clave);
    else void avisar({ tipo: "info", mensaje: "Eso no cabe en la hoja: hay que dejar espacio o achicar algo." });
  };
  const aplicarDef = (d: PlantillaDef | null) => {
    if (d) aplicar(d);
    else void avisar({ tipo: "info", mensaje: "Eso no cabe en la hoja: hay que dejar espacio o achicar algo." });
  };

  const centro = (): [number, number] => {
    const c = contenedor.current;
    if (!c || c.clientWidth === 0) return [ancho / 2, alto / 4];
    return [(c.scrollLeft + c.clientWidth / 2) / zoom, (c.scrollTop + c.clientHeight / 2) / zoom];
  };
  const mostrar = (caja: Caja) => {
    const c = contenedor.current;
    if (!c || typeof c.scrollTo !== "function") return;
    c.scrollTo({
      left: ((caja[0] + caja[2]) / 2) * zoom - c.clientWidth / 2,
      top: ((caja[1] + caja[3]) / 2) * zoom - c.clientHeight / 2,
      behavior: "smooth",
    });
  };
  const elegir = (s: NonNullable<Seleccion>, centrar = false) => {
    despachar({ t: "soltarClave" });
    setSel(s);
    if (centrar) mostrar(cajaDe(pagina, s));
  };

  // --- arrastre sobre la hoja ---------------------------------------------------------------

  function punto(e: PointerEvent): [number, number] {
    const r = svg.current!.getBoundingClientRect();
    return [((e.clientX - r.left) * ancho) / (r.width || ancho), ((e.clientY - r.top) * alto) / (r.height || alto)];
  }
  function empezar(e: PointerEvent, modo: Arrastre["modo"], s: NonNullable<Seleccion>) {
    e.stopPropagation();
    svg.current?.setPointerCapture?.(e.pointerId);
    const [x, y] = punto(e);
    arrastre.current = { modo, x, y, base: borrador, sel: s, movido: false };
    despachar({ t: "soltarClave" });
    setSel(s);
  }
  function arrastrar(e: PointerEvent) {
    const a = arrastre.current;
    if (!a) return;
    const [x, y] = punto(e);
    const dx = x - a.x;
    const dy = y - a.y;
    if (!a.movido && Math.abs(dx) + Math.abs(dy) < 2) return;
    a.movido = true;
    const base = a.base.paginas[indicePagina]!;
    let nueva: PaginaDef;
    if (a.modo === "mover") {
      nueva =
        a.sel.tipo === "celda"
          ? moverCelda(base, a.sel.tabla, a.sel.fila, a.sel.columna, dx, dy)
          : moverCabecera(base, a.sel.campo, dx, dy);
    } else {
      const [x0, y0, x1, y1] = cajaDe(base, a.sel);
      const bordes: [Borde, number][] = [
        [a.modo.includes("w") ? "x0" : "x1", (a.modo.includes("w") ? x0 : x1) + dx],
        [a.modo.includes("n") ? "y0" : "y1", (a.modo.includes("n") ? y0 : y1) + dy],
      ];
      nueva = base;
      for (const [borde, valor] of bordes) {
        nueva =
          a.sel.tipo === "celda"
            ? redimensionarCelda(nueva, a.sel.tabla, a.sel.fila, a.sel.columna, borde, valor)
            : redimensionarCabecera(nueva, a.sel.campo, borde, valor);
      }
    }
    despachar({ t: "vivo", nuevo: conPagina(a.base, indicePagina, nueva) });
  }
  function soltar() {
    const a = arrastre.current;
    arrastre.current = null;
    if (a?.movido) despachar({ t: "cerrarArrastre", base: a.base });
  }

  // --- teclado ------------------------------------------------------------------------------

  function alTeclear(e: React.KeyboardEvent) {
    if (hayDialogoAbierto()) return;
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && e.key.toLowerCase() === "z" && !esCampoDeTexto(e.target)) {
      e.preventDefault();
      despachar({ t: e.shiftKey ? "rehacer" : "deshacer" });
    } else if (ctrl && e.key.toLowerCase() === "y" && !esCampoDeTexto(e.target)) {
      e.preventDefault();
      despachar({ t: "rehacer" });
    } else if (seleccion && !esCampoDeTexto(e.target) && e.key.startsWith("Arrow")) {
      e.preventDefault();
      const paso = e.shiftKey ? 10 : 1;
      const dx = e.key === "ArrowLeft" ? -paso : e.key === "ArrowRight" ? paso : 0;
      const dy = e.key === "ArrowUp" ? -paso : e.key === "ArrowDown" ? paso : 0;
      aplicarPagina(
        seleccion.tipo === "celda"
          ? moverCelda(pagina, seleccion.tabla, seleccion.fila, seleccion.columna, dx, dy)
          : moverCabecera(pagina, seleccion.campo, dx, dy),
        "flechas",
      );
    }
  }

  // --- guardar ------------------------------------------------------------------------------

  async function guardar() {
    const ok = await confirmar({
      titulo: "Guardar la plantilla",
      mensaje:
        `Se guardará como la versión ${inicial.version + 1}. Las evaluaciones que ya hiciste siguen ` +
        `con la versión ${inicial.version}; las fotos nuevas se leerán con la corregida. ¿Guardar?`,
      confirmar: "Sí, guardar",
    });
    if (!ok) return;
    setGuardando(true);
    try {
      const r = await api.guardarVersion(inicial.id, borrador);
      try {
        window.localStorage.removeItem(claveBorrador);
      } catch {
        // nada que limpiar
      }
      await avisar({ tipo: "ok", titulo: "Plantilla guardada", mensaje: `Quedó guardada como la versión ${r.version}.` });
      alGuardar();
    } catch (e) {
      await avisar({ tipo: "error", titulo: "No se pudo guardar la plantilla", mensaje: mensajeDe(e) });
    } finally {
      setGuardando(false);
    }
  }

  /** Lo que crea una versión en el servidor (libro, página): exige no tener cambios sin guardar. */
  async function enElServidor(hacer: () => Promise<string>, falla: string) {
    setOcupadoServidor(true);
    try {
      const mensaje = await hacer();
      await avisar({ tipo: "ok", titulo: "Listo", mensaje });
      alGuardar();
    } catch (e) {
      await avisar({ tipo: "error", titulo: falla, mensaje: mensajeDe(e) });
    } finally {
      setOcupadoServidor(false);
      if (entradaLibro.current) entradaLibro.current.value = "";
      if (entradaPagina.current) entradaPagina.current.value = "";
    }
  }

  const ponerLibro = (archivo: File) =>
    enElServidor(async () => {
      const r = await api.ponerLibro(inicial.id, archivo);
      return (
        `El libro de Excel quedó como molde de la salida (versión ${r.version}). ` +
        (r.vaciar.length > 0
          ? `Antes de escribir cada evaluación se vaciarán: ${r.vaciar.join(", ")}. Revisa esa lista en «Libro de Excel» y corrígela si hace falta.`
          : "No se vaciará ninguna celda: revisa la lista en «Libro de Excel».")
      );
    }, "No se pudo usar ese libro");

  const agregarPagina = (foto: File) =>
    enElServidor(async () => {
      const r = await api.agregarPagina(inicial.id, foto);
      return `Se agregó la página ${r.paginas} con ${r.items_nuevos} ${r.tipo === "celdas" ? "celdas de respuesta" : "preguntas"} (versión ${r.version}). Es un borrador: revísala.`;
    }, "No se pudo agregar la página");

  async function borrarTabla(t: number) {
    const n = pagina.tablas[t]!.filas.length;
    const si = await confirmar({
      titulo: "Borrar la tabla",
      mensaje: `Se borrarán ${n === 1 ? "esta pregunta" : `estas ${n} filas`} de la plantilla. Puedes deshacerlo con «Deshacer».`,
      confirmar: "Sí, borrar",
      peligro: true,
    });
    if (si) {
      aplicarPagina(quitarTabla(pagina, t));
      setSel(null);
    }
  }

  // --- dibujo -------------------------------------------------------------------------------

  const lado = Math.max(8, ancho * 0.009); // manijas
  const grosor = Math.max(1.5, ancho * 0.0018);
  const sizeTexto = Math.max(11, ancho * 0.011);
  const celdaSel = seleccion?.tipo === "celda" ? seleccion : null;

  const manijas = (caja: Caja, s: NonNullable<Seleccion>) =>
    (
      [
        ["nw", caja[0], caja[1]],
        ["ne", caja[2], caja[1]],
        ["sw", caja[0], caja[3]],
        ["se", caja[2], caja[3]],
      ] as [Esquina, number, number][]
    ).map(([esq, x, y]) => (
      <rect
        key={esq}
        x={x - lado / 2}
        y={y - lado / 2}
        width={lado}
        height={lado}
        fill="white"
        stroke="#111827"
        strokeWidth={grosor}
        style={{ cursor: esq === "nw" || esq === "se" ? "nwse-resize" : "nesw-resize" }}
        onPointerDown={(e) => empezar(e, esq, s)}
      />
    ));

  const secciones = useMemo(() => {
    const grupos: { nombre: string; filas: { t: number; f: number; item: number; texto: string }[] }[] = [];
    pagina.tablas.forEach((tabla, t) => {
      const nombre = tabla.seccion || "Sin sección";
      let g = grupos[grupos.length - 1];
      if (!g || g.nombre !== nombre) {
        g = { nombre, filas: [] };
        grupos.push(g);
      }
      tabla.filas.forEach((fila, f) => g!.filas.push({ t, f, item: fila.item, texto: fila.texto }));
    });
    return grupos;
  }, [pagina]);

  return (
    <div className="flex flex-col gap-2" onKeyDown={alTeclear}>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          Nombre
          <input
            aria-label="Nombre de la plantilla"
            className="w-64 rounded-lg border border-slate-300 px-2 py-1.5 text-base"
            value={borrador.nombre}
            onChange={(e) => aplicar({ ...borrador, nombre: e.target.value }, "nombre")}
            onBlur={() => despachar({ t: "soltarClave" })}
          />
        </label>
        <span className="text-sm text-slate-600">
          Versión {inicial.version} · {contarItems(borrador)} preguntas
        </span>
        {borrador.paginas.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-slate-700">
            Página
            <select
              className="rounded-lg border border-slate-300 px-2 py-1.5 text-base"
              value={indicePagina}
              onChange={(e) => {
                setIndicePagina(Number(e.target.value));
                setSel(null);
              }}
            >
              {borrador.paginas.map((_, i) => (
                <option key={i} value={i}>
                  {i + 1}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {sinGuardar && <span className="rounded-full bg-amber-100 px-3 py-1 text-sm text-amber-900">Cambios sin guardar</span>}
          <label className="flex items-center gap-1 text-sm text-slate-700">
            Zoom
            <input
              type="range"
              aria-label="Zoom"
              min={10}
              max={250}
              value={Math.round(zoom * 100)}
              onChange={(e) => setZoom(Number(e.target.value) / 100)}
            />
          </label>
          <Boton variante="suave" disabled={estado.pasado.length === 0} onClick={() => despachar({ t: "deshacer" })}>
            Deshacer
          </Boton>
          <Boton variante="suave" disabled={estado.futuro.length === 0} onClick={() => despachar({ t: "rehacer" })}>
            Rehacer
          </Boton>
          <Boton disabled={!sinGuardar || guardando} onClick={() => void guardar()}>
            {guardando ? "Guardando…" : `Guardar como versión ${inicial.version + 1}`}
          </Boton>
        </div>
      </div>

      <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div
          ref={contenedor}
          className="overflow-auto rounded-xl border border-slate-300 bg-slate-100"
          style={{ height: "calc(100vh - 11rem)" }}
          onPointerDown={() => setSel(null)}
        >
          <svg
            ref={svg}
            role="img"
            aria-label="Hoja de la plantilla con sus casillas"
            width={ancho * zoom}
            height={alto * zoom}
            viewBox={`0 0 ${ancho} ${alto}`}
            className="block touch-none select-none"
            onPointerMove={arrastrar}
            onPointerUp={soltar}
            onPointerCancel={soltar}
          >
            <image
              href={api.urlReferencia(inicial.id, inicial.version, indicePagina)}
              width={ancho}
              height={alto}
              preserveAspectRatio="none"
            />
            {pagina.cabecera.map((c, k) => {
              const elegida = seleccion?.tipo === "cabecera" && seleccion.campo === k;
              return (
                <g key={c.campo}>
                  <rect
                    data-testid={`cabecera-${c.campo}`}
                    x={c.caja[0]}
                    y={c.caja[1]}
                    width={c.caja[2] - c.caja[0]}
                    height={c.caja[3] - c.caja[1]}
                    fill="#0ea5e9"
                    fillOpacity={elegida ? 0.25 : 0.1}
                    stroke="#0369a1"
                    strokeWidth={elegida ? grosor * 2 : grosor}
                    strokeDasharray={`${grosor * 4} ${grosor * 2}`}
                    style={{ cursor: "move" }}
                    onPointerDown={(e) => empezar(e, "mover", { tipo: "cabecera", campo: k })}
                  />
                  <text x={c.caja[0]} y={c.caja[1] - 3} fontSize={sizeTexto} fill="#0369a1" pointerEvents="none">
                    {c.campo}
                  </text>
                </g>
              );
            })}
            {pagina.tablas.map((tabla, t) => {
              const color = COLORES[t % COLORES.length]!;
              const tablaElegida = celdaSel?.tabla === t;
              return (
                <g key={t}>
                  {tabla.observacion_x &&
                    tabla.filas.map((f) => (
                      <rect
                        key={`obs-${f.item}`}
                        x={tabla.observacion_x![0]}
                        y={f.y[0]}
                        width={tabla.observacion_x![1] - tabla.observacion_x![0]}
                        height={f.y[1] - f.y[0]}
                        fill="none"
                        stroke={color}
                        strokeOpacity={0.5}
                        strokeDasharray={`${grosor * 3} ${grosor * 3}`}
                        pointerEvents="none"
                      />
                    ))}
                  {tabla.filas.map((fila, f) => (
                    <g key={fila.item}>
                      <text
                        x={tabla.columnas_x[0]![0] - 4}
                        y={(fila.y[0] + fila.y[1]) / 2 + sizeTexto / 3}
                        fontSize={sizeTexto}
                        textAnchor="end"
                        fill={color}
                        fontWeight={tablaElegida ? 700 : 500}
                        pointerEvents="none"
                      >
                        {fila.item}
                      </text>
                      {tabla.columnas_x.map((col, c) => {
                        const elegida = celdaSel?.tabla === t && celdaSel.fila === f && celdaSel.columna === c;
                        return (
                          <rect
                            key={c}
                            data-testid={`celda-${fila.item}-${c}`}
                            x={col[0]}
                            y={fila.y[0]}
                            width={col[1] - col[0]}
                            height={fila.y[1] - fila.y[0]}
                            fill={color}
                            fillOpacity={elegida ? 0.35 : tablaElegida ? 0.2 : 0.1}
                            stroke={color}
                            strokeWidth={elegida ? grosor * 2 : grosor}
                            style={{ cursor: "move" }}
                            onPointerDown={(e) => empezar(e, "mover", { tipo: "celda", tabla: t, fila: f, columna: c })}
                          >
                            <title>{`${fila.item}. ${fila.texto} — ${tabla.opciones[c]}`}</title>
                          </rect>
                        );
                      })}
                    </g>
                  ))}
                </g>
              );
            })}
            {seleccion && manijas(cajaDe(pagina, seleccion), seleccion)}
          </svg>
        </div>

        <aside ref={panel} aria-label="Propiedades" className="max-h-[calc(100vh-11rem)] space-y-3 overflow-auto rounded-xl border border-slate-200 bg-white p-3 text-sm">
          {!seleccion && (
            <div className="space-y-3">
              <p className="text-slate-700">
                Toca una casilla de la hoja para moverla o cambiar su tamaño (arrastra las esquinas), o elígela de la
                lista. Las flechas del teclado la mueven de a 1 píxel (con Mayús, de a 10).
              </p>
              <div className="flex flex-wrap gap-2">
                <Boton variante="suave" onClick={() => aplicar(agregarPreguntaSiNo(borrador, indicePagina, centro()))}>
                  Agregar pregunta Sí/No
                </Boton>
              </div>
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const p = agregarCampoCabecera(pagina, campoNuevo, centro());
                  if (p) {
                    aplicarPagina(p);
                    setCampoNuevo("");
                  } else {
                    void avisar({ tipo: "info", mensaje: "Escribe un nombre que no esté repetido para el campo." });
                  }
                }}
              >
                <label className="grow text-slate-700">
                  Campo de la cabecera
                  <input
                    className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-base"
                    value={campoNuevo}
                    placeholder="por ejemplo: cargo"
                    onChange={(e) => setCampoNuevo(e.target.value)}
                  />
                </label>
                <Boton type="submit" variante="suave">
                  Agregar
                </Boton>
              </form>

              <div className="space-y-2 border-t border-slate-200 pt-3">
                <h3 className="font-semibold">Libro de Excel</h3>
                {borrador.libro ? (
                  <label className="block text-slate-700">
                    Celda del nombre del paciente (déjala vacía si no quieres el nombre en tu hoja)
                    <input
                      aria-label="Celda del nombre del paciente"
                      placeholder="N1"
                      className="mt-1 block w-24 rounded-lg border border-slate-300 px-2 py-1.5 text-base uppercase"
                      value={borrador.libro.celda_paciente ?? ""}
                      onChange={(e) => aplicar(celdaDelPaciente(borrador, e.target.value), "celda-paciente")}
                      onBlur={() => despachar({ t: "soltarClave" })}
                    />
                  </label>
                ) : null}
                {borrador.libro ? (
                  <label className="block text-slate-700">
                    Celdas del libro que se vacían antes de escribir (rangos separados por comas)
                    <textarea
                      aria-label="Rangos que se vacían"
                      rows={2}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-base"
                      value={borrador.libro.vaciar.join(", ")}
                      onChange={(e) => aplicar(rangosAVaciar(borrador, e.target.value), "vaciar")}
                      onBlur={() => despachar({ t: "soltarClave" })}
                    />
                  </label>
                ) : (
                  <p className="text-slate-700">
                    La salida es el Excel genérico. Si tienes tu propio libro, elígelo y cada pregunta se escribe en su
                    celda.
                  </p>
                )}
                <input
                  ref={entradaLibro}
                  type="file"
                  aria-label="Elegir el libro de Excel"
                  accept=".xlsx"
                  disabled={sinGuardar || ocupadoServidor}
                  className="block text-base"
                  onChange={(e) => {
                    const archivo = e.target.files?.[0];
                    if (archivo) void ponerLibro(archivo);
                  }}
                />
                <h3 className="pt-1 font-semibold">Páginas ({borrador.paginas.length})</h3>
                <p className="text-slate-700">Agrega el reverso u otra hoja del formulario desde una foto.</p>
                <input
                  ref={entradaPagina}
                  type="file"
                  aria-label="Agregar una página desde una foto"
                  accept="image/jpeg,image/png"
                  disabled={sinGuardar || ocupadoServidor}
                  className="block text-base"
                  onChange={(e) => {
                    const foto = e.target.files?.[0];
                    if (foto) void agregarPagina(foto);
                  }}
                />
                {sinGuardar && (
                  <p className="text-sm text-amber-800">Guarda los cambios antes de cambiar el libro o agregar una página.</p>
                )}
              </div>
            </div>
          )}

          {seleccion?.tipo === "cabecera" && (
            <PanelCabecera
              pagina={pagina}
              k={seleccion.campo}
              aplicarPagina={aplicarPagina}
              alQuitar={() => {
                aplicarPagina(quitarCampoCabecera(pagina, seleccion.campo));
                setSel(null);
              }}
              avisar={(m) => void avisar({ tipo: "info", mensaje: m })}
            />
          )}

          {celdaSel && (
            <PanelTabla
              plantilla={borrador}
              indicePagina={indicePagina}
              sel={celdaSel}
              elegir={elegir}
              aplicarPagina={aplicarPagina}
              aplicarDef={aplicarDef}
              alBorrarTabla={() => void borrarTabla(celdaSel.tabla)}
              soltar={() => despachar({ t: "soltarClave" })}
            />
          )}

          {seleccion && (
            <Boton variante="suave" onClick={() => setSel(null)}>
              Listo con esta casilla
            </Boton>
          )}

          <div>
            <h3 className="mb-1 font-semibold">Preguntas</h3>
            {secciones.length === 0 && <p className="text-slate-600">Esta página no tiene preguntas.</p>}
            <div className="space-y-2">
              {secciones.map((g, i) => (
                <details key={`${g.nombre}-${i}`} open={g.filas.some((r) => r.t === celdaSel?.tabla)}>
                  <summary className="cursor-pointer text-slate-800">
                    {g.nombre} <span className="text-slate-500">({g.filas.length})</span>
                  </summary>
                  <ul className="mt-1 space-y-0.5">
                    {g.filas.map((r) => (
                      <li key={r.item}>
                        <button
                          type="button"
                          className={`w-full truncate rounded px-2 py-1 text-left hover:bg-slate-100 ${
                            celdaSel?.tabla === r.t && celdaSel.fila === r.f ? "bg-sky-100" : ""
                          }`}
                          onClick={() => elegir({ tipo: "celda", tabla: r.t, fila: r.f, columna: 0 }, true)}
                        >
                          {r.item}. {r.texto || "(sin texto)"}
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Numero({
  etiqueta,
  valor,
  alCambiar,
}: {
  etiqueta: string;
  valor: number;
  alCambiar: (v: number) => void;
}) {
  return (
    <label className="text-xs text-slate-600">
      {etiqueta}
      <input
        type="number"
        className="mt-0.5 block w-full rounded border border-slate-300 px-1.5 py-1 text-sm"
        value={valor}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) alCambiar(v);
        }}
      />
    </label>
  );
}

function CajaNumerica({ caja, alCambiar }: { caja: Caja; alCambiar: (borde: Borde, v: number) => void }) {
  return (
    <div className="grid grid-cols-4 gap-1">
      <Numero etiqueta="Izq." valor={caja[0]} alCambiar={(v) => alCambiar("x0", v)} />
      <Numero etiqueta="Arriba" valor={caja[1]} alCambiar={(v) => alCambiar("y0", v)} />
      <Numero etiqueta="Der." valor={caja[2]} alCambiar={(v) => alCambiar("x1", v)} />
      <Numero etiqueta="Abajo" valor={caja[3]} alCambiar={(v) => alCambiar("y1", v)} />
    </div>
  );
}

function PanelCabecera({
  pagina,
  k,
  aplicarPagina,
  alQuitar,
  avisar,
}: {
  pagina: PaginaDef;
  k: number;
  aplicarPagina: (p: PaginaDef | null, clave?: string) => void;
  alQuitar: () => void;
  avisar: (mensaje: string) => void;
}) {
  const campo = pagina.cabecera[k]!;
  const [nombre, setNombre] = useState(campo.campo);
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">Campo de la cabecera</h3>
      <label className="block text-slate-700">
        Nombre del campo
        <input
          className="mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-base"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onBlur={() => {
            if (nombre === campo.campo) return;
            const p = renombrarCampoCabecera(pagina, k, nombre);
            if (p) aplicarPagina(p);
            else {
              avisar("Ese nombre está vacío o ya lo usa otro campo.");
              setNombre(campo.campo);
            }
          }}
        />
      </label>
      <CajaNumerica
        caja={campo.caja}
        alCambiar={(borde, v) => aplicarPagina(redimensionarCabecera(pagina, k, borde, v), `cab-${k}-${borde}`)}
      />
      <Boton variante="suave" onClick={alQuitar}>
        Quitar este campo
      </Boton>
    </div>
  );
}

function PanelTabla({
  plantilla,
  indicePagina,
  sel,
  elegir,
  aplicarPagina,
  aplicarDef,
  alBorrarTabla,
  soltar,
}: {
  plantilla: PlantillaDef;
  indicePagina: number;
  sel: { tipo: "celda"; tabla: number; fila: number; columna: number };
  elegir: (s: NonNullable<Seleccion>, centrar?: boolean) => void;
  aplicarPagina: (p: PaginaDef | null, clave?: string) => void;
  aplicarDef: (d: PlantillaDef | null) => void;
  alBorrarTabla: () => void;
  soltar: () => void;
}) {
  const pagina = plantilla.paginas[indicePagina]!;
  const tabla = pagina.tablas[sel.tabla]!;
  const fila = tabla.filas[sel.fila]!;
  const campo = "mt-1 block w-full rounded-lg border border-slate-300 px-2 py-1.5 text-base";
  const hayLibro = Boolean(plantilla.libro);
  return (
    <div className="space-y-3">
      <h3 className="font-semibold">
        Pregunta {fila.item} · {tabla.opciones[sel.columna]}
      </h3>
      <label className="block text-slate-700">
        Sección
        <input
          className={campo}
          value={tabla.seccion ?? ""}
          onChange={(e) => aplicarPagina(seccionDeTabla(pagina, sel.tabla, e.target.value), `sec-${sel.tabla}`)}
          onBlur={soltar}
        />
      </label>
      <div>
        <p className="text-slate-700">Casilla «{tabla.opciones[sel.columna]}» (píxeles de la hoja)</p>
        <CajaNumerica
          caja={cajaDeCelda(pagina, sel.tabla, sel.fila, sel.columna)}
          alCambiar={(borde, v) =>
            aplicarPagina(
              redimensionarCelda(pagina, sel.tabla, sel.fila, sel.columna, borde, v),
              `celda-${sel.tabla}-${sel.fila}-${sel.columna}-${borde}`,
            )
          }
        />
      </div>

      {tabla.tipo === "digito" ? (
        <p className="text-slate-700">
          Número escrito a mano. Dígitos permitidos: <strong>{tabla.opciones.join(", ")}</strong>.
          La celda del número es la casilla de la hoja.
        </p>
      ) : (
      <div>
        <p className="mb-1 font-medium text-slate-800">Opciones (columnas)</p>
        <ul className="space-y-1">
          {tabla.opciones.map((op, c) => (
            <li key={c} className="flex items-center gap-1">
              <input
                aria-label={`Opción ${c + 1}`}
                className="min-w-0 grow rounded border border-slate-300 px-2 py-1 text-base"
                value={op}
                onFocus={() => elegir({ tipo: "celda", tabla: sel.tabla, fila: sel.fila, columna: c })}
                onChange={(e) => aplicarPagina(renombrarOpcion(pagina, sel.tabla, c, e.target.value), `op-${sel.tabla}-${c}`)}
                onBlur={soltar}
              />
              <button
                type="button"
                aria-label={`Quitar la opción ${op}`}
                className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
                disabled={tabla.opciones.length <= 1}
                onClick={() => aplicarPagina(quitarColumna(pagina, sel.tabla, c))}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
        <Boton variante="suave" className="mt-1" onClick={() => aplicarPagina(agregarColumna(pagina, sel.tabla))}>
          Agregar opción
        </Boton>
      </div>
      )}

      <div>
        <p className="mb-1 font-medium text-slate-800">Filas de esta tabla</p>
        <ul className="space-y-1">
          {tabla.filas.map((f, i) => (
            <li key={f.item} className={`flex items-center gap-1 rounded ${i === sel.fila ? "bg-sky-50" : ""}`}>
              <span className="w-7 text-right text-slate-500">{f.item}</span>
              <input
                aria-label={`Texto de la fila ${f.item}`}
                className="min-w-0 grow rounded border border-slate-300 px-2 py-1 text-base"
                value={f.texto}
                onFocus={() => elegir({ tipo: "celda", tabla: sel.tabla, fila: i, columna: sel.columna })}
                onChange={(e) => aplicarPagina(textoDeFila(pagina, sel.tabla, i, e.target.value), `txt-${f.item}`)}
                onBlur={soltar}
              />
              {hayLibro && (
                <input
                  aria-label={`Celda del Excel de la fila ${f.item}`}
                  placeholder="A1"
                  className="w-16 shrink-0 rounded border border-slate-300 px-1.5 py-1 text-base uppercase"
                  value={f.celda ?? ""}
                  onFocus={() => elegir({ tipo: "celda", tabla: sel.tabla, fila: i, columna: sel.columna })}
                  onChange={(e) => aplicarPagina(celdaDeFila(pagina, sel.tabla, i, e.target.value), `cel-${f.item}`)}
                  onBlur={soltar}
                />
              )}
              <button
                type="button"
                aria-label={`Quitar la fila ${f.item}`}
                className="rounded px-2 py-1 text-slate-600 hover:bg-slate-100"
                onClick={() => aplicarPagina(quitarFila(pagina, sel.tabla, i))}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
        <Boton variante="suave" className="mt-1" onClick={() => aplicarDef(agregarFila(plantilla, indicePagina, sel.tabla))}>
          Agregar fila
        </Boton>
      </div>

      <Boton variante="suave" onClick={alBorrarTabla}>
        Borrar toda esta tabla
      </Boton>
    </div>
  );
}
