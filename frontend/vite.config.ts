/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Las pruebas que teclean formularios enteros rozan los 5 s por defecto cuando la máquina está ocupada.
    testTimeout: 15_000,
    // Solo la hoja de estilos leída como texto por sus pruebas; el resto del CSS no se procesa.
    css: { include: [/styles\.css\?raw$/] },
  },
});
