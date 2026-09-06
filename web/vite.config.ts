import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend so the browser only
// ever talks to one origin (works in local dev AND in sandboxed previews).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: [".e2b.app", "localhost"],
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
