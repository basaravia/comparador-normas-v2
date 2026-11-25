import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Pruebas de componentes React (D-49, decisión del usuario del 25 nov 2026). La lógica pura sigue con `node --test` (pruebas/*.test.ts):
// vitest solo recoge pruebas/componentes/**, así que no se pisan.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["pruebas/componentes/**/*.test.tsx"],
    setupFiles: ["pruebas/componentes/configuracion.ts"],
  },
});
