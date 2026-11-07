import type { PlantillaDef } from "../api/tipos";

/** Estado del editor: la plantilla que se está corrigiendo y su historial para deshacer/rehacer. */
export interface EstadoEditor {
  borrador: PlantillaDef;
  pasado: PlantillaDef[];
  futuro: PlantillaDef[];
  /** Mientras se escribe en el mismo campo, los cambios cuentan como un solo paso del historial. */
  clave: string | null;
}

export type AccionEditor =
  | { t: "aplicar"; nuevo: PlantillaDef; clave?: string }
  | { t: "vivo"; nuevo: PlantillaDef } // durante un arrastre: se ve, pero aún no es un paso
  | { t: "cerrarArrastre"; base: PlantillaDef }
  | { t: "soltarClave" }
  | { t: "deshacer" }
  | { t: "rehacer" }
  | { t: "reiniciar"; nuevo: PlantillaDef };

const MAXIMO_HISTORIAL = 100;

export function estadoInicial(borrador: PlantillaDef): EstadoEditor {
  return { borrador, pasado: [], futuro: [], clave: null };
}

export function reducirEditor(s: EstadoEditor, a: AccionEditor): EstadoEditor {
  switch (a.t) {
    case "aplicar":
      if (a.clave && s.clave === a.clave) return { ...s, borrador: a.nuevo };
      return {
        borrador: a.nuevo,
        pasado: [...s.pasado.slice(-(MAXIMO_HISTORIAL - 1)), s.borrador],
        futuro: [],
        clave: a.clave ?? null,
      };
    case "vivo":
      return { ...s, borrador: a.nuevo };
    case "cerrarArrastre":
      return {
        ...s,
        pasado: [...s.pasado.slice(-(MAXIMO_HISTORIAL - 1)), a.base],
        futuro: [],
        clave: null,
      };
    case "soltarClave":
      return s.clave === null ? s : { ...s, clave: null };
    case "deshacer": {
      const anterior = s.pasado[s.pasado.length - 1];
      if (!anterior) return s;
      return {
        borrador: anterior,
        pasado: s.pasado.slice(0, -1),
        futuro: [s.borrador, ...s.futuro],
        clave: null,
      };
    }
    case "rehacer": {
      const [siguiente, ...resto] = s.futuro;
      if (!siguiente) return s;
      return { borrador: siguiente, pasado: [...s.pasado, s.borrador], futuro: resto, clave: null };
    }
    case "reiniciar":
      return estadoInicial(a.nuevo);
  }
}
