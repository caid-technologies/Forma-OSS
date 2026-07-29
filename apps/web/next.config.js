const path = require("path");
const { loadEnvConfig } = require("@next/env");

// Keep one shared environment surface at the repository root after moving the
// web application under apps/. Next still loads app-local overrides normally.
loadEnvConfig(path.resolve(__dirname, "../.."));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
};

module.exports = nextConfig;
