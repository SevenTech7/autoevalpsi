import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface Estado {
  error: Error | null;
}

/** Si algo se rompe al dibujar la pantalla, se dice en vez de dejar la ventana en blanco. */
export class LimiteDeErrores extends Component<{ children: ReactNode }, Estado> {
  state: Estado = { error: null };

  static getDerivedStateFromError(error: Error): Estado {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("La pantalla falló:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto mt-16 max-w-xl space-y-3 rounded-lg border border-red-300 bg-red-50 p-6">
        <h1 className="text-xl font-semibold text-red-900">AutoEvalPsi no pudo mostrar esta pantalla</h1>
        <p>Cierra la ventana y vuelve a abrir AutoEvalPsi. Si pasa otra vez, cuéntalo con este detalle:</p>
        <pre className="overflow-auto rounded bg-white p-3 text-sm">{this.state.error.message}</pre>
        <button
          type="button"
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium hover:bg-slate-50"
          onClick={() => window.location.reload()}
        >
          Volver a cargar
        </button>
      </div>
    );
  }
}
