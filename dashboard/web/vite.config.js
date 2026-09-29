import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built into ../dist and served by dashboard/server.py (no dev server needed on stage; works offline).
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "../dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
