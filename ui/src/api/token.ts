const CLAVE = "autoevalpsi.token";

/**
 * El token de la app llega en la URL de arranque (`/?token=…`, AP-R3). Se guarda para la sesión de
 * la ventana y se quita de la barra de direcciones. Devuelve null si no hay ninguno.
 */
export function obtenerToken(
  ubicacion: Pick<Location, "search" | "pathname" | "hash"> = window.location,
  almacen: Pick<Storage, "getItem" | "setItem"> = sessionStorage,
  historial: Pick<History, "replaceState"> = window.history,
): string | null {
  const enUrl = new URLSearchParams(ubicacion.search).get("token");
  if (enUrl) {
    try {
      almacen.setItem(CLAVE, enUrl);
    } catch {
      // sin almacenamiento: vale para esta carga
    }
    historial.replaceState(null, "", `${ubicacion.pathname}${ubicacion.hash}`);
    return enUrl;
  }
  try {
    return almacen.getItem(CLAVE);
  } catch {
    return null;
  }
}
