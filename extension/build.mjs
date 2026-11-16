// Builds the extension into dist/. dist/config.json is written by `webpilot setup` and is never touched here.
import * as esbuild from "esbuild";
import { createHash } from "node:crypto";
import { copyFileSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";

const watch = process.argv.includes("--watch");
mkdirSync("dist", { recursive: true });
copyFileSync("manifest.json", "dist/manifest.json");
copyFileSync("popup.html", "dist/popup.html");

// Build id: a hash of what the build reads. background.js carries it, and dist/build.json says which build is on
// disk; the extension compares the two to notice it was rebuilt but not reloaded (badge OLD, a hint in errors).
// In --watch mode it is taken once at start, so rebuilds by the watcher are not told apart.
const sources = ["build.mjs", "manifest.json", "popup.html", "package-lock.json",
  ...readdirSync("src", { recursive: true }).map((f) => `src/${f.replaceAll("\\", "/")}`)
    .filter((f) => statSync(f).isFile()).sort()];
const hash = createHash("sha256");
for (const f of sources) hash.update(f).update("\0").update(readFileSync(f)).update("\0");
const build = hash.digest("hex").slice(0, 12);

const common = { bundle: true, target: "chrome120", logLevel: "info", define: { __WP_BUILD__: JSON.stringify(build) } };
const builds = [
  // Service worker: WebSocket bridge + command dispatch.
  { ...common, entryPoints: ["src/background.ts"], outfile: "dist/background.js", format: "esm" },
  // Injected into pages on demand; exposes globalThis.__wp.
  { ...common, entryPoints: ["src/page.ts"], outfile: "dist/page.js", format: "iife" },
  // Injected into pages (main world) during actions and navigations: answers alert/confirm/prompt.
  { ...common, entryPoints: ["src/dialogs.ts"], outfile: "dist/dialogs.js", format: "iife" },
  // Injected into a frame (main world) while upload clicks a button that makes its file input in script.
  { ...common, entryPoints: ["src/filehook.ts"], outfile: "dist/filehook.js", format: "iife" },
  // Toolbar popup: connection state and profile name.
  { ...common, entryPoints: ["src/popup.ts"], outfile: "dist/popup.js", format: "iife" },
];

if (watch) {
  for (const b of builds) await (await esbuild.context(b)).watch();
} else {
  await Promise.all(builds.map((b) => esbuild.build(b)));
}
writeFileSync("dist/build.json", JSON.stringify({ build }) + "\n");
