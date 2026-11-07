import type {
  Configuracion,
  EstadoCola,
  Evaluacion,
  InicioVinculo,
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
    if (cuerpo !== undefined) {
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
    borrarFotos: (evaluacion: string, incluirRecortes = false) =>
      pedir<{ borrados: number }>("POST", `/api/evaluaciones/${id(evaluacion)}/borrar_fotos`, {
        incluir_recortes: incluirRecortes,
      }),
    plantillas: () => pedir<ResumenPlantilla[]>("GET", "/api/plantillas"),
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
