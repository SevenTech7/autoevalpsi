/** Lo que el escritorio (pywebview) expone en `window.pywebview.api` (app/escritorio.py: Puente).
 * Fuera de la ventana (navegador, pruebas) no existe y las pantallas usan su alternativa. */
interface PuenteEscritorio {
  elegir_carpeta_exportacion: () => Promise<string | null>;
  abrir_carpeta: (ruta: string) => Promise<boolean>;
}

function puente(): Partial<PuenteEscritorio> | undefined {
  return (window as unknown as { pywebview?: { api?: Partial<PuenteEscritorio> } }).pywebview?.api;
}

/** Diálogo nativo para elegir la carpeta de los Excel; guarda la elegida. null: cancelado. */
export function elegirCarpetaNativa(): (() => Promise<string | null>) | null {
  const f = puente()?.elegir_carpeta_exportacion;
  return f ? () => f.call(puente()) : null;
}

/** Abre una carpeta en el Explorador, si estamos en la ventana de escritorio. */
export function abrirCarpetaNativa(): ((ruta: string) => Promise<boolean>) | null {
  const f = puente()?.abrir_carpeta;
  return f ? (ruta) => f.call(puente(), ruta) : null;
}
