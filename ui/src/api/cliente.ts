import type {
  Configuracion,
  EstadoCola,
  CambioEvaluacion,
  Evaluacion,
  InicioVinculo,
  Plantilla,
  PlantillaDef,
  ResultadoDesdeFoto,
  ResultadoLibro,
  ResultadoPagina,
  ResultadoExportacion,
  ResumenEvaluacion,
  ResumenPlantilla,
  Salud,
  Vinculo,
} from "./tipos";

/** Error con el formato `{detail: {codigo, mensaje}}` del servidor; `message` es apto para la usuaria. */
export class ErrorApi extends Error {
  readonly estado: number;
  readonly codigo: string;
  constructor(estado: number, codigo: string, mensaje: string) {
    super(mensaje);
    this.name = "ErrorApi";
    this.estado = estado;
    this.codigo = codigo;
  }
}

export interface OpcionesCliente {
  token: string;
  base?: string;
  fetcher?: typeof fetch;
}

async function leerError(respuesta: Response): Promise<ErrorApi> {
  try {
    const cuerpo = (await respuesta.json()) as { detail?: { codigo?: string; mensaje?: string } };
    const d = cuerpo.detail;
    if (d && typeof d === "object" && d.mensaje) {
      return new ErrorApi(respuesta.status, d.codigo ?? "error", d.mensaje);
    }
  } catch {
    // cuerpo que no es JSON: cae al mensaje genérico
  }
  return new ErrorApi(
    respuesta.status,
    "error",
    `La aplicación respondió con un error (${respuesta.status}).`,
  );
}

/** Cliente tipado de la API. Siempre llama con el token de la app (la ventana de la laptop). */
export function crearCliente({ token, base = "", fetcher }: OpcionesCliente) {
  async function pedir<T>(metodo: string, ruta: string, cuerpo?: unknown): Promise<T> {
    const hacer = fetcher ?? fetch;
    const cabeceras: Record<string, string> = { Authorization: `Bearer ${token}` };
    const init: RequestInit = { method: metodo, headers: cabeceras };
    if (cuerpo instanceof FormData) {
      init.body = cuerpo; // el navegador pone el tipo y el límite del multipart
    } else if (cuerpo !== undefined) {
      cabeceras["Content-Type"] = "application/json";
      init.body = JSON.stringify(cuerpo);
    }
    let respuesta: Response;
    try {
      respuesta = await hacer(`${base}${ruta}`, init);
    } catch {
      throw new ErrorApi(
        0,
        "sin_conexion",
        "No se pudo hablar con la aplicación. Ciérrala y ábrela de nuevo.",
      );
    }
    if (!respuesta.ok) throw await leerError(respuesta);
    return (await respuesta.json()) as T;
  }

  const id = encodeURIComponent;
  return {
    salud: () => pedir<Salud>("GET", "/api/salud"),
    cola: () => pedir<EstadoCola>("GET", "/api/cola"),
    evaluaciones: () => pedir<ResumenEvaluacion[]>("GET", "/api/evaluaciones"),
    evaluacion: (evaluacion: string) =>
      pedir<Evaluacion>("GET", `/api/evaluaciones/${id(evaluacion)}`),
    plantilla: (plantilla: string, version: number) =>
      pedir<Plantilla>("GET", `/api/plantillas/${id(plantilla)}?version=${version}`),
    corregirEvaluacion: (evaluacion: string, cambio: CambioEvaluacion) =>
      pedir<Evaluacion>("PUT", `/api/evaluaciones/${id(evaluacion)}`, cambio),
    eliminarEvaluacion: (evaluacion: string) =>
      pedir<{ eliminada: boolean }>("DELETE", `/api/evaluaciones/${id(evaluacion)}`),
    descartarPagina: (evaluacion: string, pagina: number) =>
      pedir<{ evaluacion_eliminada: boolean }>(
        "DELETE",
        `/api/evaluaciones/${id(evaluacion)}/paginas/${pagina}`,
      ),
    /** URL de un recorte para un `<img>`, que no puede mandar cabeceras: el token va en la URL. */
    urlRecorteFila: (evaluacion: string, item: number) =>
      `${base}/api/evaluaciones/${id(evaluacion)}/recortes/${item}?token=${id(token)}`,
    urlRecorteCabecera: (evaluacion: string, campo: string) =>
      `${base}/api/evaluaciones/${id(evaluacion)}/cabecera/${id(campo)}?token=${id(token)}`,
    exportar: (evaluacion: string, iniciales = false) =>
      pedir<ResultadoExportacion>("POST", `/api/evaluaciones/${id(evaluacion)}/exportar`, { iniciales }),
    borrarFotos: (evaluacion: string, incluirRecortes = false) =>
      pedir<{ borrados: number }>("POST", `/api/evaluaciones/${id(evaluacion)}/borrar_fotos`, {
        incluir_recortes: incluirRecortes,
      }),
    plantillas: () => pedir<ResumenPlantilla[]>("GET", "/api/plantillas"),
    /** La plantilla completa (cajas incluidas) para el editor; sin `version`, la más nueva. */
    plantillaDef: (plantilla: string, version?: number) =>
      pedir<PlantillaDef>(
        "GET",
        `/api/plantillas/${id(plantilla)}${version === undefined ? "" : `?version=${version}`}`,
      ),
    /** Fondo del editor: la imagen en blanco de una página (el `<img>` pide con el token en la URL). */
    urlReferencia: (plantilla: string, version: number, pagina: number) =>
      `${base}/api/plantillas/${id(plantilla)}/referencia/${pagina}?version=${version}&token=${id(token)}`,
    /** Guarda la plantilla corregida como versión nueva; devuelve el resumen de esa versión. */
    guardarVersion: (plantilla: string, definicion: PlantillaDef) =>
      pedir<ResumenPlantilla>("POST", `/api/plantillas/${id(plantilla)}/versiones`, {
        plantilla: definicion,
      }),
    plantillaDesdeFoto: (foto: File, nombre: string) => {
      const form = new FormData();
      form.append("foto", foto);
      form.append("nombre", nombre);
      return pedir<ResultadoDesdeFoto>("POST", "/api/plantillas/desde-foto", form);
    },
    /** El libro de Excel de la usuaria pasa a ser el molde de la salida (versión nueva). */
    ponerLibro: (plantilla: string, archivo: File) => {
      const form = new FormData();
      form.append("archivo", archivo);
      return pedir<ResultadoLibro>("POST", `/api/plantillas/${id(plantilla)}/libro`, form);
    },
    /** Una página más para la plantilla (por ejemplo el reverso), armada desde otra foto. */
    agregarPagina: (plantilla: string, foto: File) => {
      const form = new FormData();
      form.append("foto", foto);
      return pedir<ResultadoPagina>("POST", `/api/plantillas/${id(plantilla)}/paginas`, form);
    },
    importarPlantilla: (archivo: File) => {
      const form = new FormData();
      form.append("archivo", archivo);
      return pedir<ResumenPlantilla>("POST", "/api/plantillas/importar", form);
    },
    vinculo: () => pedir<Vinculo>("GET", "/api/vinculo"),
    iniciarVinculo: (ip?: string) =>
      pedir<InicioVinculo>("POST", `/api/vinculo/iniciar${ip ? `?ip=${id(ip)}` : ""}`),
    desvincular: () => pedir<{ desvinculado: boolean }>("DELETE", "/api/vinculo"),
    configuracion: () => pedir<Configuracion>("GET", "/api/configuracion"),
    guardarCarpetaExportacion: (carpeta: string) =>
      pedir<Configuracion>("PUT", "/api/configuracion", { carpeta_exportacion: carpeta }),
  };
}

export type Cliente = ReturnType<typeof crearCliente>;
