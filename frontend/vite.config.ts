import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only ever talks to the Vite dev server. Calls to /api are proxied
// to the FastAPI backend, so there is no cross-origin request and no CORS to set up.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // API_URL lets you point the dev proxy at another port, e.g. when 8000 is busy.
        target: process.env.API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
