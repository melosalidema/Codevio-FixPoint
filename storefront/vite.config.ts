import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The storefront is a customer-facing demo app. It calls the Platzi Fake Store
// API directly (that API sends `access-control-allow-origin: *`) and proxies
// Fixpoint API calls to the backend on port 8000, exactly like the operator
// console does. The proxy keeps the browser requests same-origin, so the
// backend's CORS allow-list does not need a new entry.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  // `npm run preview` mirrors the dev proxy so the built bundle can be
  // exercised against the backend without CORS changes.
  preview: {
    port: 4173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
