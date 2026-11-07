import { describe, expect, it, vi } from "vitest";

import { ErrorApi, crearCliente } from "../api/cliente";
import { obtenerToken } from "../api/token";
import { analizarRuta } from "../ruta";

function respuesta(cuerpo: unknown, estado = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status: estado });
}

describe("cliente de la API", () => {
  it("manda el token en cada llamada y el cuerpo como JSON", async () => {
    const fetcher = vi.fn().mockResolvedValue(respuesta({ borrados: 2 }));
    const api = crearCliente({ token: "t0k3n", fetcher });
    expect(await api.borrarFotos("ev 1", true)).toEqual({ borrados: 2 });
    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/evaluaciones/ev%201/borrar_fotos");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ incluir_recortes: true }));
    const cabeceras = init.headers as Record<string, string>;
    expect(cabeceras.Authorization).toBe("Bearer t0k3n");
    expect(cabeceras["Content-Type"]).toBe("application/json");
  });

  it("no manda Content-Type cuando no hay cuerpo", async () => {
    const fetcher = vi.fn().mockResolvedValue(respuesta([]));
    await crearCliente({ token: "t", fetcher }).evaluaciones();
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeUndefined();
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("elige la IP del QR por parámetro", async () => {
    const fetcher = vi.fn().mockResolvedValue(respuesta({}));
    await crearCliente({ token: "t", fetcher }).iniciarVinculo("192.168.1.20");
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/vinculo/iniciar?ip=192.168.1.20");
  });

  it("convierte el error del servidor en ErrorApi con su mensaje para la usuaria", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(respuesta({ detail: { codigo: "carpeta_invalida", mensaje: "No sirve esa carpeta." } }, 422));
    const api = crearCliente({ token: "t", fetcher });
    const e = await api.guardarCarpetaExportacion("x").catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ErrorApi);
    expect(e).toMatchObject({ estado: 422, codigo: "carpeta_invalida", message: "No sirve esa carpeta." });
  });

  it("un error sin JSON da un mensaje genérico, y sin red avisa que reabra la app", async () => {
    const api = crearCliente({
      token: "t",
      fetcher: vi.fn().mockResolvedValue(new Response("<html>", { status: 500 })),
    });
    await expect(api.salud()).rejects.toMatchObject({ estado: 500, message: expect.stringContaining("500") });

    const sinRed = crearCliente({ token: "t", fetcher: vi.fn().mockRejectedValue(new TypeError("red")) });
    await expect(sinRed.salud()).rejects.toMatchObject({ codigo: "sin_conexion" });
  });
});

describe("token de la app", () => {
  const ubic = (search: string) => ({ search, pathname: "/", hash: "#/evaluaciones" });

  it("lo toma de la URL, lo guarda y limpia la barra de direcciones", () => {
    const almacen = { getItem: vi.fn(), setItem: vi.fn() };
    const historial = { replaceState: vi.fn() };
    expect(obtenerToken(ubic("?token=abc123"), almacen, historial)).toBe("abc123");
    expect(almacen.setItem).toHaveBeenCalledWith("autoevalpsi.token", "abc123");
    expect(historial.replaceState).toHaveBeenCalledWith(null, "", "/#/evaluaciones");
  });

  it("sin token en la URL usa el de la sesión; sin ninguno devuelve null", () => {
    const historial = { replaceState: vi.fn() };
    const con = { getItem: vi.fn().mockReturnValue("guardado"), setItem: vi.fn() };
    expect(obtenerToken(ubic(""), con, historial)).toBe("guardado");
    expect(historial.replaceState).not.toHaveBeenCalled();
    const sin = { getItem: vi.fn().mockReturnValue(null), setItem: vi.fn() };
    expect(obtenerToken(ubic(""), sin, historial)).toBeNull();
  });

  it("si el almacenamiento falla no se cae", () => {
    const roto = {
      getItem: vi.fn(() => {
        throw new Error("bloqueado");
      }),
      setItem: vi.fn(() => {
        throw new Error("bloqueado");
      }),
    };
    const historial = { replaceState: vi.fn() };
    expect(obtenerToken(ubic("?token=zzz"), roto, historial)).toBe("zzz");
    expect(obtenerToken(ubic(""), roto, historial)).toBeNull();
  });
});

describe("rutas", () => {
  it("reconoce cada pantalla y cae en el inicio", () => {
    expect(analizarRuta("")).toEqual({ pantalla: "inicio" });
    expect(analizarRuta("#/")).toEqual({ pantalla: "inicio" });
    expect(analizarRuta("#/evaluaciones")).toEqual({ pantalla: "evaluaciones" });
    expect(analizarRuta("#/evaluaciones/ab%20c")).toEqual({ pantalla: "evaluacion", id: "ab c" });
    expect(analizarRuta("#/configuracion")).toEqual({ pantalla: "configuracion" });
    expect(analizarRuta("#/cosa-rara")).toEqual({ pantalla: "inicio" });
  });
});
