import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/settings/",
  server: {
    host: "0.0.0.0",
    port: 5174,
    proxy: {
      "/api": { target: "http://127.0.0.1:9892", changeOrigin: true },
    },
  },
});
