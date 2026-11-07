import { useMemo } from "react";

import { crearCliente } from "./api/cliente";
import { Aviso } from "./componentes/base";
import { ContextoApi } from "./hooks";
import { Configuracion } from "./pantallas/Configuracion";
import { PantallaEvaluacion, PantallaEvaluaciones } from "./pantallas/Evaluaciones";
import { Inicio } from "./pantallas/Inicio";
import { enlace, useRuta, type Ruta } from "./ruta";

const MENU: { texto: string; href: string; pantallas: Ruta["pantalla"][] }[] = [
  { texto: "Inicio", href: enlace.inicio, pantallas: ["inicio"] },
  { texto: "Evaluaciones", href: enlace.evaluaciones, pantallas: ["evaluaciones", "evaluacion"] },
  { texto: "Configuración", href: enlace.configuracion, pantallas: ["configuracion"] },
];

function Pantalla({ ruta }: { ruta: Ruta }) {
  switch (ruta.pantalla) {
    case "inicio":
      return <Inicio />;
    case "evaluaciones":
      return <PantallaEvaluaciones />;
    case "evaluacion":
      return <PantallaEvaluacion id={ruta.id} />;
    case "configuracion":
      return <Configuracion />;
  }
}

export function App({ token }: { token: string | null }) {
  const ruta = useRuta();
  const api = useMemo(() => (token ? crearCliente({ token }) : null), [token]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold text-acento">AutoEvalPsi</h1>
        <nav aria-label="Principal" className="flex gap-2">
          {MENU.map((m) => {
            const activa = m.pantallas.includes(ruta.pantalla);
            return (
              <a
                key={m.href}
                href={m.href}
                aria-current={activa ? "page" : undefined}
                className={`rounded-lg px-4 py-2 text-base font-medium ${
                  activa ? "bg-acento text-white" : "text-tinta hover:bg-slate-200"
                }`}
              >
                {m.texto}
              </a>
            );
          })}
        </nav>
      </header>
      <main>
        {api ? (
          <ContextoApi.Provider value={api}>
            <Pantalla ruta={ruta} />
          </ContextoApi.Provider>
        ) : (
          <Aviso>
            Esta página debe abrirse desde la aplicación AutoEvalPsi. Cierra esta ventana y abre la aplicación
            desde su acceso directo.
          </Aviso>
        )}
      </main>
    </div>
  );
}
