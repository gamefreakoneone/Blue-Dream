import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiPrefixes = [
  "/query",
  "/conversation",
  "/memory",
  "/reminders",
  "/proactive",
  "/devices",
  "/alerts",
  "/geofence",
  "/push",
  "/storage",
  "/capture",
];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      apiPrefixes.map((prefix) => [prefix, "http://localhost:8000"]),
    ),
  },
});
