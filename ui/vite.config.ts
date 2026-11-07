import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// La salida va a donde FastAPI sirve la interfaz (app/servidor.py: ESTATICOS).
// base "/" porque la ventana abre http://127.0.0.1:<puerto>/ y los archivos cuelgan de /assets.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/",
  build: {
    outDir: "../src/autoevalpsi/app/estaticos",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    // En desarrollo con `npm run dev`, la API real corre en la app de escritorio.
    proxy: { "/api": "http://host.docker.internal:8765" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/pruebas.setup.ts"],
    css: false,
  },
});
