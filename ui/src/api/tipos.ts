// Espejo tipado del contrato HTTP v1 (docstring de app/servidor.py y dataclasses de app/datos.py).

export type EstadoEvaluacion = "pendiente" | "revisada" | "exportada";

export interface ResumenEvaluacion {
  id: string;
  plantilla_id: string;
  paciente: string;
  fecha: string;
  estado: EstadoEvaluacion;
  creada_en: string;
  n_filas: number;
  filas_pendientes: number;
}

export interface PaginaGuardada {
  pagina: number;
  foto_sha256: string;
  foto_ruta: string | null; // null: la foto se borró (AP-D1)
  problemas_calidad: string[];
  registro: Record<string, unknown>;
  ocr_activo: boolean;
}

export interface FilaGuardada {
  item: number;
  pagina: number;
  opcion_leida: string | null;
  opcion: string | null;
  banderas: string[];
  texto_ocr: string;
  observacion: string;
  ruta_recorte: string | null;
  revisada: boolean;
}

export interface Evaluacion {
  id: string;
  plantilla_id: string;
  plantilla_version: number;
  paciente: string;
  fecha: string;
  cabecera: Record<string, string>;
  recortes_cabecera: Record<string, string>;
  cabecera_revisada: boolean;
  estado: EstadoEvaluacion;
  creada_en: string;
  actualizada_en: string;
  paginas: PaginaGuardada[];
  filas: FilaGuardada[];
  filas_pendientes: number;
}

export interface Salud {
  ok: boolean;
  pendientes: number;
}

export interface EstadoCola {
  pendientes: number;
  en_cola: number;
  procesando: number;
  lista: number;
  error: number;
}

export interface Vinculo {
  vinculado: boolean;
  creado: string | null;
  ultimo_uso: string | null;
}

export interface InicioVinculo {
  url: string | null;
  qr_svg: string | null;
  ip: string | null;
  puerto: number;
  ips: string[];
  vence_en: number; // segundos de validez al emitirlo
  vinculado: boolean;
  mensaje: string;
}

export interface Configuracion {
  carpeta_exportacion: string | null;
  carpeta_exportacion_efectiva: string;
}

export interface ResultadoExportacion {
  carpeta: string;
  evaluacion: string;
  consolidado: string;
}

export interface ResumenPlantilla {
  id: string;
  nombre: string;
  version: number;
  paginas: number;
  items: number;
}

/** Lo que la revisión necesita de la plantilla: textos de los ítems y sus opciones. */
export interface Plantilla {
  id: string;
  nombre: string;
  version: number;
  paginas: {
    cabecera: { campo: string }[];
    tablas: {
      tipo?: "marcas" | "digito"; // «digito»: un número escrito a mano, no una casilla
      opciones: string[];
      observacion_x?: number[] | null; // si la hoja tiene columna de observación
      filas: { item: number; texto: string }[];
    }[];
  }[];
}

export interface CambioFila {
  item: number;
  opcion?: string | null; // null = «sin respuesta»; ausente = no tocar
  observacion?: string;
}

export interface CambioEvaluacion {
  paciente?: string;
  cabecera?: Record<string, string>;
  confirmar_cabecera?: boolean;
  filas?: CambioFila[];
}

// --- plantilla completa (editor, FS-R3): espejo de `core/plantilla.py` --------------------------

export type Intervalo = [number, number];
export type Caja = [number, number, number, number];

export interface FilaDef {
  item: number;
  texto: string;
  y: Intervalo;
  celda?: string | null; // celda del libro de Excel donde va el valor («A19»)
}

/** El libro de Excel de la usuaria, que sirve de molde de la salida. */
export interface LibroDef {
  archivo: string;
  hoja?: string | null;
  vaciar: string[]; // rangos que se limpian antes de escribir la evaluación
}

export interface TablaDef {
  tipo?: "marcas" | "digito"; // «digito»: un número manuscrito en una sola celda
  seccion?: string | null;
  opciones: string[];
  columnas_x: Intervalo[];
  observacion_x?: Intervalo | null;
  filas: FilaDef[];
}

export interface CampoCabeceraDef {
  campo: string;
  caja: Caja;
  tipo?: "texto";
}

export interface PaginaDef {
  imagen_referencia: string;
  tamano_px: [number, number];
  cabecera: CampoCabeceraDef[];
  tablas: TablaDef[];
}

export interface PlantillaDef {
  esquema_version: number;
  id: string;
  nombre: string;
  version: number;
  omr: { tinta_minima: number; margen_relativo: number };
  libro?: LibroDef | null;
  paginas: PaginaDef[];
}

export interface ResultadoLibro extends ResumenPlantilla {
  vaciar: string[];
}

export interface ResultadoPagina extends ResumenPlantilla {
  items_nuevos: number;
  tipo: "si_no" | "celdas";
}

export interface ResultadoDesdeFoto extends ResumenPlantilla {
  secciones: number;
  tipo?: "si_no" | "celdas"; // lo que se encontró: preguntas Sí/No o una cuadrícula de celdas numeradas
}
