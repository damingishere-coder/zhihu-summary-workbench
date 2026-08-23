import { cp, mkdir, rm } from "node:fs/promises";
import { build } from "esbuild";

const outdir = new URL("../dist/extension/", import.meta.url);
await rm(outdir, { recursive: true, force: true });
await mkdir(outdir, { recursive: true });
await Promise.all([
  build({ entryPoints: ["extension/src/background.ts"], outfile: "dist/extension/background.js", bundle: true, format: "iife", platform: "browser", target: "chrome120" }),
  build({ entryPoints: ["extension/src/content.ts"], outfile: "dist/extension/content.js", bundle: true, format: "iife", platform: "browser", target: "chrome120" }),
  build({ entryPoints: ["extension/src/popup.ts"], outfile: "dist/extension/popup.js", bundle: true, format: "iife", platform: "browser", target: "chrome120" }),
]);
await Promise.all([
  cp("extension/manifest.json", "dist/extension/manifest.json"),
  cp("extension/popup.html", "dist/extension/popup.html"),
  cp("extension/popup.css", "dist/extension/popup.css"),
]);
