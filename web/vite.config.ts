import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Built files are served by the FastAPI app at "/", so API calls are same-origin. In dev, proxy them.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: { proxy: { "/investigate": "http://localhost:8000", "/jobs": "http://localhost:8000", "/healthz": "http://localhost:8000" } },
  build: { outDir: "dist", emptyOutDir: true },
})
