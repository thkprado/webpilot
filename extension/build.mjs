// Builds the extension into dist/. dist/config.json is written by `webpilot setup` and is never touched here.
import * as esbuild from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";

const watch = process.argv.includes("--watch");
mkdirSync("dist", { recursive: true });
copyFileSync("manifest.json", "dist/manifest.json");
copyFileSync("popup.html", "dist/popup.html");

const common = { bundle: true, target: "chrome120", logLevel: "info" };
const builds = [
  // Service worker: WebSocket bridge + command dispatch.
  { ...common, entryPoints: ["src/background.ts"], outfile: "dist/background.js", format: "esm" },
  // Injected into pages on demand; exposes globalThis.__wp.
  { ...common, entryPoints: ["src/page.ts"], outfile: "dist/page.js", format: "iife" },
  // Toolbar popup: connection state and profile name.
  { ...common, entryPoints: ["src/popup.ts"], outfile: "dist/popup.js", format: "iife" },
];

if (watch) {
  for (const b of builds) await (await esbuild.context(b)).watch();
} else {
  await Promise.all(builds.map((b) => esbuild.build(b)));
}
