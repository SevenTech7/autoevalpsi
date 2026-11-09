import type { Cliente } from "../api/cliente";
import type { Evaluacion, FilaGuardada, InicioVinculo, Plantilla, ResumenEvaluacion } from "../api/tipos";

export function plantilla(): Plantilla {
  return {
    id: "evaluacion-continua",
    nombre: "Evaluación Continua",
    version: 1,
    paginas: [
      {
        cabecera: [{ campo: "paciente" }, { campo: "fecha" }],
        tablas: [
          {
            opciones: ["A", "B", "C"],
            filas: [
              { item: 1, texto: "Puntualidad" },
              { item: 2, texto: "Trato con el equipo" },
              { item: 3, texto: "Orden del puesto" },
            ],
          },
        ],
      },
    ],
  };
}

export function fila(parcial: Partial<FilaGuardada> = {}): FilaGuardada {
  return {
    item: 1,
    pagina: 0,
    opcion_leida: "A",
    opcion: "A",
    banderas: [],
    texto_ocr: "",
    observacion: "",
    ruta_recorte: null,
    revisada: true,
    ...parcial,
  };
}

/** Tres filas: la 1 revisada, la 2 con doble marca y OCR dudoso, la 3 sin marca. */
export function evaluacion(parcial: Partial<Evaluacion> = {}): Evaluacion {
  const filas = [
    fila({ item: 1, opcion: "A" }),
    fila({
      item: 2,
      opcion: null,
      opcion_leida: null,
      banderas: ["doble_marca", "ocr_confianza_baja"],
      texto_ocr: "llega tarde",
      observacion: "llega tarde",
      ruta_recorte: "recortes/ev1/item_2.png",
      revisada: false,
    }),
    fila({ item: 3, opcion: null, opcion_leida: null, banderas: ["sin_marca"], revisada: false }),
  ];
  return {
    id: "ev1",
    plantilla_id: "evaluacion-continua",
    plantilla_version: 1,
    paciente: "Ana Pérez",
    fecha: "2026-11-07",
    cabecera: { fecha: "5/11" },
    recortes_cabecera: { paciente: "recortes/ev1/cabecera_paciente.png" },
    cabecera_revisada: false,
    estado: "pendiente",
    creada_en: "2026-11-07T10:30:00",
    actualizada_en: "2026-11-07T10:30:00",
    paginas: [
      {
        pagina: 0,
        foto_sha256: "a".repeat(64),
        foto_ruta: "fotos/ev1/0.jpg",
        problemas_calidad: [],
        registro: {},
        ocr_activo: true,
      },
    ],
    filas,
    filas_pendientes: 2,
    ...parcial,
  };
}

export function resumen(parcial: Partial<ResumenEvaluacion> = {}): ResumenEvaluacion {
  return {
    id: "ev1",
    plantilla_id: "evaluacion-continua",
    paciente: "Ana Pérez",
    fecha: "2026-11-07",
    estado: "pendiente",
    creada_en: "2026-11-07T10:30:00",
    n_filas: 12,
    filas_pendientes: 3,
    paginas_total: 1,
    paginas_subidas: 1,
    ...parcial,
  };
}

export function inicioVinculo(parcial: Partial<InicioVinculo> = {}): InicioVinculo {
  return {
    url: "http://192.168.1.20:8765/captura?vinculo=abc",
    qr_svg: "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
    ip: "192.168.1.20",
    puerto: 8765,
    ips: ["192.168.1.20"],
    vence_en: 300,
    vinculado: false,
    mensaje: "",
    ...parcial,
  };
}

/** Un cliente de mentira: cada método es un `vi.fn` que el test configura. */
export function clienteFalso(sobre: Partial<Cliente> = {}): Cliente {
  const sinUsar = () => Promise.reject(new Error("no esperado en este test"));
  return {
    salud: sinUsar,
    cola: sinUsar,
    evaluaciones: sinUsar,
    evaluacion: sinUsar,
    exportar: sinUsar,
    borrarFotos: sinUsar,
    plantilla: sinUsar,
    corregirEvaluacion: sinUsar,
    descartarPagina: sinUsar,
    eliminarEvaluacion: sinUsar,
    subirFoto: sinUsar,
    eliminarPlantilla: sinUsar,
    urlRecorteFila: (e: string, i: number) => `/recorte/${e}/${i}`,
    urlRecorteCabecera: (e: string, c: string) => `/cabecera/${e}/${c}`,
    plantillas: sinUsar,
    plantillaDef: sinUsar,
    urlReferencia: (p: string, v: number, n: number) => `/referencia/${p}/${v}/${n}`,
    guardarVersion: sinUsar,
    ponerLibro: sinUsar,
    agregarPagina: sinUsar,
    plantillaDesdeFoto: sinUsar,
    importarPlantilla: sinUsar,
    vinculo: sinUsar,
    iniciarVinculo: sinUsar,
    desvincular: sinUsar,
    configuracion: sinUsar,
    guardarCarpetaExportacion: sinUsar,
    actualizacion: () =>
      Promise.resolve({ actual: "0.1.0", buscada: false, novedad: null, estado: "libre", bajado: 0, mensaje: "" }),
    buscarActualizacion: sinUsar,
    descargarActualizacion: sinUsar,
    instalarActualizacion: sinUsar,
    ...sobre,
  } as Cliente;
}
