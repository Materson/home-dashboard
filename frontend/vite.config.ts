import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import { VitePWA } from "vite-plugin-pwa";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      manifest: {
        name: "Home Dashboard",
        short_name: "Home",
        description: "Family dashboard",
        theme_color: "#4c6ef5",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  resolve: {
    // package.json is "type": "module", so no __dirname — resolve from this file's URL.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: false },
      "/admin": { target: "http://localhost:8000", changeOrigin: false },
      "/static": { target: "http://localhost:8000", changeOrigin: false },
      "/media": { target: "http://localhost:8000", changeOrigin: false },
      "/healthz": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});
