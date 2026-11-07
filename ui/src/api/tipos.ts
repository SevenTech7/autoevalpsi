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
    tablas: { opciones: string[]; filas: { item: number; texto: string }[] }[];
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
