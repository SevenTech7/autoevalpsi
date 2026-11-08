/**
 * FS-R3: lógica pura del editor de plantillas. Nada de React ni de DOM: cada función recibe la
 * página (o la plantilla) y devuelve una copia nueva, o `null` si la operación no cabe. Las
 * restricciones espejan las del servidor (`core/plantilla.py`): columnas y filas ordenadas y sin
 * solaparse, la observación a la derecha de las columnas, todo dentro de la imagen.
 */
import type { Caja, CampoCabeceraDef, Intervalo, PaginaDef, PlantillaDef, TablaDef } from "../api/tipos";

export const MINIMO = 6; // px de la imagen: lado mínimo de una caja
const SEPARACION = 4;

export type Borde = "x0" | "x1" | "y0" | "y1";

export type Seleccion =
  | { tipo: "celda"; tabla: number; fila: number; columna: number }
  | { tipo: "cabecera"; campo: number }
  | null;

const limitar = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);
const copiar = <T,>(x: T): T => structuredClone(x);

// --- límites ---------------------------------------------------------------------------------

export function limitesColumna(p: PaginaDef, t: number, c: number): Intervalo {
  const tabla = p.tablas[t]!;
  const lo = c > 0 ? tabla.columnas_x[c - 1]![1] : 0;
  const hi =
    c < tabla.columnas_x.length - 1
      ? tabla.columnas_x[c + 1]![0]
      : (tabla.observacion_x?.[0] ?? p.tamano_px[0]);
  return [lo, hi];
}

export function limitesFila(p: PaginaDef, t: number, f: number): Intervalo {
  const tabla = p.tablas[t]!;
  const lo = f > 0 ? tabla.filas[f - 1]!.y[1] : 0;
  const hi = f < tabla.filas.length - 1 ? tabla.filas[f + 1]!.y[0] : p.tamano_px[1];
  return [lo, hi];
}

/** La caja de una celda: su columna por su fila. */
export function cajaDeCelda(p: PaginaDef, t: number, f: number, c: number): Caja {
  const tabla = p.tablas[t]!;
  const [x0, x1] = tabla.columnas_x[c]!;
  const [y0, y1] = tabla.filas[f]!.y;
  return [x0, y0, x1, y1];
}

// --- celdas ----------------------------------------------------------------------------------

/** Mueve la celda: desplaza su columna (todas las filas de la tabla) y su fila (todas las columnas). */
export function moverCelda(p: PaginaDef, t: number, f: number, c: number, dx: number, dy: number): PaginaDef {
  const nueva = copiar(p);
  const tabla = nueva.tablas[t]!;
  const [cx0, cx1] = tabla.columnas_x[c]!;
  const [lx, hx] = limitesColumna(p, t, c);
  const mx = limitar(Math.round(dx), lx - cx0, hx - cx1);
  tabla.columnas_x[c] = [cx0 + mx, cx1 + mx];
  const [fy0, fy1] = tabla.filas[f]!.y;
  const [ly, hy] = limitesFila(p, t, f);
  const my = limitar(Math.round(dy), ly - fy0, hy - fy1);
  tabla.filas[f]!.y = [fy0 + my, fy1 + my];
  return nueva;
}

/** Lleva un borde de la celda a `valor`, sin cruzar a la vecina ni dejar la caja más chica que `MINIMO`. */
export function redimensionarCelda(
  p: PaginaDef,
  t: number,
  f: number,
  c: number,
  borde: Borde,
  valor: number,
): PaginaDef {
  const nueva = copiar(p);
  const tabla = nueva.tablas[t]!;
  if (borde === "x0" || borde === "x1") {
    const [lo, hi] = limitesColumna(p, t, c);
    const col = tabla.columnas_x[c]!;
    if (borde === "x0") col[0] = limitar(Math.round(valor), lo, col[1] - MINIMO);
    else col[1] = limitar(Math.round(valor), col[0] + MINIMO, hi);
  } else {
    const [lo, hi] = limitesFila(p, t, f);
    const y = tabla.filas[f]!.y;
    if (borde === "y0") y[0] = limitar(Math.round(valor), lo, y[1] - MINIMO);
    else y[1] = limitar(Math.round(valor), y[0] + MINIMO, hi);
  }
  return nueva;
}

// --- cabecera --------------------------------------------------------------------------------

export function moverCabecera(p: PaginaDef, k: number, dx: number, dy: number): PaginaDef {
  const nueva = copiar(p);
  const [ancho, alto] = p.tamano_px;
  const [x0, y0, x1, y1] = nueva.cabecera[k]!.caja;
  const mx = limitar(Math.round(dx), -x0, ancho - x1);
  const my = limitar(Math.round(dy), -y0, alto - y1);
  nueva.cabecera[k]!.caja = [x0 + mx, y0 + my, x1 + mx, y1 + my];
  return nueva;
}

export function redimensionarCabecera(p: PaginaDef, k: number, borde: Borde, valor: number): PaginaDef {
  const nueva = copiar(p);
  const [ancho, alto] = p.tamano_px;
  const caja = nueva.cabecera[k]!.caja;
  const v = Math.round(valor);
  if (borde === "x0") caja[0] = limitar(v, 0, caja[2] - MINIMO);
  else if (borde === "x1") caja[2] = limitar(v, caja[0] + MINIMO, ancho);
  else if (borde === "y0") caja[1] = limitar(v, 0, caja[3] - MINIMO);
  else caja[3] = limitar(v, caja[1] + MINIMO, alto);
  return nueva;
}

export function agregarCampoCabecera(p: PaginaDef, nombre: string, centro: [number, number]): PaginaDef | null {
  const campo = nombre.trim();
  if (!campo || p.cabecera.some((c) => c.campo === campo)) return null;
  const nueva = copiar(p);
  const [ancho, alto] = p.tamano_px;
  const w = Math.round(ancho * 0.25);
  const h = Math.round(ancho * 0.03);
  const x0 = limitar(Math.round(centro[0] - w / 2), 0, ancho - w);
  const y0 = limitar(Math.round(centro[1] - h / 2), 0, alto - h);
  const nuevoCampo: CampoCabeceraDef = { campo, caja: [x0, y0, x0 + w, y0 + h], tipo: "texto" };
  nueva.cabecera.push(nuevoCampo);
  return nueva;
}

export function quitarCampoCabecera(p: PaginaDef, k: number): PaginaDef {
  const nueva = copiar(p);
  nueva.cabecera.splice(k, 1);
  return nueva;
}

export function renombrarCampoCabecera(p: PaginaDef, k: number, nombre: string): PaginaDef | null {
  const campo = nombre.trim();
  if (!campo || p.cabecera.some((c, i) => i !== k && c.campo === campo)) return null;
  const nueva = copiar(p);
  nueva.cabecera[k]!.campo = campo;
  return nueva;
}

// --- tablas, filas y columnas ----------------------------------------------------------------

export function siguienteItem(plantilla: PlantillaDef): number {
  let maximo = 0;
  for (const pg of plantilla.paginas) for (const t of pg.tablas) for (const f of t.filas) maximo = Math.max(maximo, f.item);
  return maximo + 1;
}

/** Una tabla nueva de una fila con «Sí» y «No», centrada en `centro` (coordenadas de la imagen). */
export function agregarPreguntaSiNo(
  plantilla: PlantillaDef,
  pagina: number,
  centro: [number, number],
  seccion?: string | null,
): PlantillaDef {
  const nueva = copiar(plantilla);
  const p = nueva.paginas[pagina]!;
  const [ancho, alto] = p.tamano_px;
  const lado = Math.max(MINIMO * 2, Math.round(ancho * 0.02));
  const separacion = lado;
  const total = lado * 2 + separacion;
  const x0 = limitar(Math.round(centro[0] - total / 2), 0, ancho - total);
  const y0 = limitar(Math.round(centro[1] - lado / 2), 0, alto - lado);
  const tabla: TablaDef = {
    seccion: seccion ?? null,
    opciones: ["Sí", "No"],
    columnas_x: [
      [x0, x0 + lado],
      [x0 + lado + separacion, x0 + total],
    ],
    observacion_x: null,
    filas: [{ item: siguienteItem(plantilla), texto: "Pregunta nueva", y: [y0, y0 + lado] }],
  };
  p.tablas.push(tabla);
  return nueva;
}

export function quitarTabla(p: PaginaDef, t: number): PaginaDef {
  const nueva = copiar(p);
  nueva.tablas.splice(t, 1);
  return nueva;
}

/** Agrega una fila debajo de la última, del mismo alto. `null` si no cabe en la imagen. */
export function agregarFila(plantilla: PlantillaDef, pagina: number, t: number): PlantillaDef | null {
  const nueva = copiar(plantilla);
  const p = nueva.paginas[pagina]!;
  const tabla = p.tablas[t]!;
  const ultima = tabla.filas[tabla.filas.length - 1]!;
  const alto = ultima.y[1] - ultima.y[0];
  const y0 = ultima.y[1] + SEPARACION;
  if (y0 + alto > p.tamano_px[1]) return null;
  tabla.filas.push({ item: siguienteItem(plantilla), texto: "Fila nueva", y: [y0, y0 + alto] });
  return nueva;
}

/** Quita una fila; si era la última de la tabla, quita la tabla. */
export function quitarFila(p: PaginaDef, t: number, f: number): PaginaDef {
  const nueva = copiar(p);
  const tabla = nueva.tablas[t]!;
  if (tabla.filas.length === 1) nueva.tablas.splice(t, 1);
  else tabla.filas.splice(f, 1);
  return nueva;
}

/** Agrega una opción (columna) a la derecha de la última, del mismo ancho. `null` si no cabe. */
export function agregarColumna(p: PaginaDef, t: number): PaginaDef | null {
  const nueva = copiar(p);
  const tabla = nueva.tablas[t]!;
  const ultima = tabla.columnas_x[tabla.columnas_x.length - 1]!;
  const ancho = ultima[1] - ultima[0];
  const x0 = ultima[1] + SEPARACION;
  const tope = tabla.observacion_x?.[0] ?? p.tamano_px[0];
  if (x0 + ancho > tope) return null;
  tabla.columnas_x.push([x0, x0 + ancho]);
  tabla.opciones.push(`Opción ${tabla.opciones.length + 1}`);
  return nueva;
}

/** Quita una opción; `null` si es la única (una tabla necesita al menos una). */
export function quitarColumna(p: PaginaDef, t: number, c: number): PaginaDef | null {
  const tabla = p.tablas[t]!;
  if (tabla.columnas_x.length <= 1) return null;
  const nueva = copiar(p);
  nueva.tablas[t]!.columnas_x.splice(c, 1);
  nueva.tablas[t]!.opciones.splice(c, 1);
  return nueva;
}

export function renombrarOpcion(p: PaginaDef, t: number, c: number, nombre: string): PaginaDef {
  const nueva = copiar(p);
  nueva.tablas[t]!.opciones[c] = nombre;
  return nueva;
}

export function textoDeFila(p: PaginaDef, t: number, f: number, texto: string): PaginaDef {
  const nueva = copiar(p);
  nueva.tablas[t]!.filas[f]!.texto = texto;
  return nueva;
}

export function celdaDeFila(p: PaginaDef, t: number, f: number, celda: string): PaginaDef {
  const nueva = copiar(p);
  nueva.tablas[t]!.filas[f]!.celda = celda.trim().toUpperCase() || null;
  return nueva;
}

/** «A1:L58, I63:I71» → ["A1:L58", "I63:I71"]: separa por comas, punto y coma o saltos de línea. */
export function rangosDeTexto(texto: string): string[] {
  return texto
    .split(/[\s,;]+/)
    .map((r) => r.trim().toUpperCase())
    .filter(Boolean);
}

export function rangosAVaciar(plantilla: PlantillaDef, texto: string): PlantillaDef {
  if (!plantilla.libro) return plantilla;
  return { ...plantilla, libro: { ...plantilla.libro, vaciar: rangosDeTexto(texto) } };
}

export function celdaDelPaciente(plantilla: PlantillaDef, celda: string): PlantillaDef {
  if (!plantilla.libro) return plantilla;
  return { ...plantilla, libro: { ...plantilla.libro, celda_paciente: celda.trim().toUpperCase() || null } };
}

export function seccionDeTabla(p: PaginaDef, t: number, seccion: string): PaginaDef {
  const nueva = copiar(p);
  nueva.tablas[t]!.seccion = seccion.trim() || null;
  return nueva;
}

/** Selección que sigue válida tras un cambio (por ejemplo, tras quitar una fila). */
export function seleccionValida(p: PaginaDef, s: Seleccion): Seleccion {
  if (!s) return null;
  if (s.tipo === "cabecera") return s.campo < p.cabecera.length ? s : null;
  const tabla = p.tablas[s.tabla];
  if (!tabla || s.fila >= tabla.filas.length || s.columna >= tabla.columnas_x.length) return null;
  return s;
}

/** Cuántas preguntas hay en toda la plantilla (para el resumen). */
export function contarItems(plantilla: PlantillaDef): number {
  return plantilla.paginas.reduce((n, pg) => n + pg.tablas.reduce((m, t) => m + t.filas.length, 0), 0);
}
