var _a;
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// The dev server proxies /api to the FastAPI backend so the browser only
// ever talks to one origin (works in local dev AND in sandboxed previews).
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": {
                target: (_a = process.env.VITE_API_TARGET) !== null && _a !== void 0 ? _a : "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: false,
    },
});
