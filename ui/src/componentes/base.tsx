import type { ComponentPropsWithRef, ReactNode } from "react";

export function Tarjeta({
  titulo,
  children,
  acciones,
}: {
  titulo: string;
  children: ReactNode;
  acciones?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="text-xl font-semibold">{titulo}</h2>
        {acciones}
      </div>
      {children}
    </section>
  );
}

type PropsBoton = ComponentPropsWithRef<"button"> & { variante?: "principal" | "suave" };

export function Boton({ variante = "principal", className = "", ...resto }: PropsBoton) {
  const estilo =
    variante === "principal"
      ? "bg-acento text-white hover:bg-acento-oscuro"
      : "border border-slate-300 bg-white text-tinta hover:bg-slate-50";
  return (
    <button
      type="button"
      className={`rounded-lg px-4 py-2.5 text-base font-medium disabled:cursor-not-allowed disabled:opacity-50 ${estilo} ${className}`}
      {...resto}
    />
  );
}

export function Aviso({ tipo = "error", children }: { tipo?: "error" | "info" | "ok"; children: ReactNode }) {
  const colores = {
    error: "border-red-200 bg-red-50 text-red-900",
    info: "border-sky-200 bg-sky-50 text-sky-900",
    ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[tipo];
  return (
    <p role={tipo === "error" ? "alert" : "status"} className={`rounded-lg border px-4 py-3 ${colores}`}>
      {children}
    </p>
  );
}
