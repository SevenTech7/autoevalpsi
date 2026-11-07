import type { Cliente } from "../api/cliente";
import type { InicioVinculo, ResumenEvaluacion } from "../api/tipos";

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
    borrarFotos: sinUsar,
    plantillas: sinUsar,
    vinculo: sinUsar,
    iniciarVinculo: sinUsar,
    desvincular: sinUsar,
    configuracion: sinUsar,
    guardarCarpetaExportacion: sinUsar,
    ...sobre,
  } as Cliente;
}
