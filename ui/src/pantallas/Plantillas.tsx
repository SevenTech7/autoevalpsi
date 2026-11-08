import { useRef, useState } from "react";

import type { ResumenPlantilla } from "../api/tipos";
import { Aviso, Boton, Tarjeta } from "../componentes/base";
import { useDialogos } from "../componentes/Dialogos";
import { mensajeDe, useApi, useCarga } from "../hooks";
import { enlace } from "../ruta";

/** Una fila por plantilla: su versión más nueva (las anteriores siguen guardadas para lo ya leído). */
export function ultimasVersiones(todas: ResumenPlantilla[]): ResumenPlantilla[] {
  const porId = new Map<string, ResumenPlantilla>();
  for (const p of todas) {
    const previa = porId.get(p.id);
    if (!previa || p.version > previa.version) porId.set(p.id, p);
  }
  return [...porId.values()].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
}

function DesdeFoto({ alCrear }: { alCrear: (id: string) => void }) {
  const api = useApi();
  const { avisar } = useDialogos();
  const [nombre, setNombre] = useState("");
  const [foto, setFoto] = useState<File | null>(null);
  const [leyendo, setLeyendo] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  async function crear() {
    if (!foto) return;
    setLeyendo(true);
    try {
      const r = await api.plantillaDesdeFoto(foto, nombre);
      setNombre("");
      setFoto(null);
      if (entrada.current) entrada.current.value = "";
      await avisar({
        tipo: "ok",
        titulo: "Borrador listo",
        mensaje:
          `Encontré ${r.items} ${r.tipo === "celdas" ? "celdas de respuesta" : "preguntas"} en ` +
          `${r.secciones} ${r.secciones === 1 ? "sección" : "secciones"}. Es un borrador: revísalo en el ` +
          "editor y corrige lo que falte o esté mal.",
      });
      alCrear(r.id);
    } catch (e) {
      await avisar({ tipo: "error", titulo: "No se pudo armar la plantilla", mensaje: mensajeDe(e) });
    } finally {
      setLeyendo(false);
    }
  }

  return (
    <Tarjeta titulo="Crear una plantilla desde una foto">
      <div className="space-y-4">
        <p>
          Sube la foto de un formulario <strong>ya lleno</strong>. La aplicación busca las preguntas «Sí / No» o las
          celdas numeradas con números escritos a mano y arma un borrador; después lo corriges tú en el editor. Con la hoja entera, derecha y bien
          iluminada sale mejor.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="grow text-sm text-slate-700">
            Nombre del formulario
            <input
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-base"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
            />
          </label>
          <label className="text-sm text-slate-700">
            Foto del formulario lleno
            <input
              ref={entrada}
              type="file"
              accept="image/jpeg,image/png"
              className="mt-1 block text-base"
              onChange={(e) => setFoto(e.target.files?.[0] ?? null)}
            />
          </label>
          <Boton disabled={!foto || !nombre.trim() || leyendo} onClick={() => void crear()}>
            {leyendo ? "Leyendo la foto…" : "Armar el borrador"}
          </Boton>
        </div>
        {leyendo && <Aviso tipo="info">Leyendo la foto: puede tardar unos segundos.</Aviso>}
      </div>
    </Tarjeta>
  );
}

function ImportarZip({ alImportar }: { alImportar: () => void }) {
  const api = useApi();
  const { avisar } = useDialogos();
  const entrada = useRef<HTMLInputElement>(null);

  async function importar(archivo: File) {
    try {
      const r = await api.importarPlantilla(archivo);
      await avisar({ tipo: "ok", titulo: "Plantilla importada", mensaje: `«${r.nombre}» (versión ${r.version}) quedó instalada.` });
      alImportar();
    } catch (e) {
      await avisar({ tipo: "error", titulo: "No se pudo importar", mensaje: mensajeDe(e) });
    } finally {
      if (entrada.current) entrada.current.value = "";
    }
  }

  return (
    <Tarjeta titulo="Importar una plantilla (.zip)">
      <label className="text-sm text-slate-700">
        Archivo .zip con la plantilla y su imagen en blanco
        <input
          ref={entrada}
          type="file"
          accept=".zip,application/zip"
          className="mt-1 block text-base"
          onChange={(e) => {
            const archivo = e.target.files?.[0];
            if (archivo) void importar(archivo);
          }}
        />
      </label>
    </Tarjeta>
  );
}

export function Plantillas() {
  const api = useApi();
  const lista = useCarga(() => api.plantillas());
  const ultimas = ultimasVersiones(lista.datos ?? []);

  return (
    <div className="space-y-6">
      <Tarjeta titulo="Plantillas instaladas">
        {lista.error && <Aviso>{lista.error}</Aviso>}
        {lista.datos && ultimas.length === 0 && (
          <p>Todavía no hay plantillas. Crea una desde la foto de un formulario lleno, o importa un .zip.</p>
        )}
        <ul className="divide-y divide-slate-200">
          {ultimas.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div>
                <p className="text-lg font-medium">{p.nombre}</p>
                <p className="text-sm text-slate-600">
                  Versión {p.version} · {p.items} preguntas · {p.paginas} {p.paginas === 1 ? "página" : "páginas"}
                </p>
              </div>
              <a
                href={enlace.plantilla(p.id)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-base font-medium hover:bg-slate-50"
              >
                Editar
              </a>
            </li>
          ))}
        </ul>
      </Tarjeta>
      <DesdeFoto
        alCrear={(id) => {
          window.location.hash = enlace.plantilla(id);
        }}
      />
      <ImportarZip alImportar={lista.recargar} />
    </div>
  );
}
