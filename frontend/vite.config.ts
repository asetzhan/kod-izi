import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Used only when running `npm run dev` without docker; in docker Nginx routes /api.
    proxy: { "/api": process.env.VITE_API_PROXY ?? "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
