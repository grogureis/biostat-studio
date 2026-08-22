import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  test: {
    exclude: ["e2e/**", "**/node_modules/**", "**/dist/**"],
  },
});
