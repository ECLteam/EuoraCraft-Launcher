import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    target: "chrome100",
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("framer-motion")) return "framer-motion";
          if (id.includes("react-router-dom") || id.includes("react-dom") || id.includes("react/")) return "react-vendor";
          if (id.includes("i18next") || id.includes("react-i18next")) return "i18n";
          if (id.includes("@radix-ui")) return "radix";
        },
      },
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
});