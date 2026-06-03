#!/usr/bin/env node
/* build_bullveda.js — precompile the multi-file BullVeda prototype into ONE
 * self-contained HTML with NO in-browser Babel (sub-second boot vs ~12s).
 *
 * Strategy: keep the prototype 1:1. For each CSS <link>, inline the file. For
 * each JSX <script>, esbuild-transform JSX→JS and emit it as its own inline
 * <script> in the SAME order — preserving the classic-script global-sharing
 * semantics exactly. boot.js (plain) is inlined as-is. React/ReactDOM/charts
 * stay on CDN; the @babel/standalone CDN is dropped. Real-data sync-fetch in
 * boot.js is unchanged, so the bundle must still be SERVED from :7432.
 *
 * Usage: node build_bullveda.js   (run from infra/prototype/bullveda/)
 */
const fs = require("fs");
const path = require("path");
const esbuild = require("/tmp/bvbuild/node_modules/esbuild");

const DIR = __dirname;
const SRC = path.join(DIR, "BullVeda.dev.html"); // the multi-file loader (build source)
const OUT = path.join(DIR, "BullVeda.html");      // the shipped fast bundle (what users open)

let html = fs.readFileSync(SRC, "utf8");

// 1) collect ordered CSS hrefs + JS srcs from the loader
const cssHrefs = [...html.matchAll(/<link[^>]+href="([^"]+\.css)(?:\?[^"]*)?"/g)].map(m => m[1]);
const babelSrcs = [...html.matchAll(/<script[^>]+type="text\/babel"[^>]+src="([^"]+)"/g)].map(m => m[1]);

// 2) inline CSS
const cssBlocks = cssHrefs.map(href => {
  const p = path.join(DIR, href);
  if (!fs.existsSync(p)) { console.warn("  · missing CSS", href); return `/* missing: ${href} */`; }
  return `/* ===== ${href} ===== */\n` + fs.readFileSync(p, "utf8");
}).join("\n");

// 3) transform each JSX/JS module (per-file, JSX loader) → inline <script>
let nTx = 0;
const jsBlocks = babelSrcs.map(src => {
  const p = path.join(DIR, src);
  if (!fs.existsSync(p)) { console.warn("  · missing JS", src); return ""; }
  const code = fs.readFileSync(p, "utf8");
  const loader = src.endsWith(".jsx") ? "jsx" : "js";
  const out = esbuild.transformSync(code, { loader, jsx: "transform", target: "es2018" });
  nTx++;
  return `<script>/* ${src} */\n${out.code}</script>`;
}).join("\n");

// 4) boot.js (plain, synchronous real-data adapter) inlined as-is
const bootJs = fs.readFileSync(path.join(DIR, "bullveda-boot.js"), "utf8");

// 5) reusable head bits from the original loader
const fonts = `<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />`;
const cdn = `<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js" crossorigin="anonymous"></script>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>`;
// preserve the bundler thumbnail template + root; inject an instant loading
// screen into #root so the user sees something while the sync data loads
// (the end-of-body scripts block paint until they finish).
const bodyMatch = html.match(/<body>([\s\S]*?)<\/body>/);
let body = bodyMatch ? bodyMatch[1] : '<div id="root"></div>';
const LOADING = `<div id="bv-loading" style="position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:#0a0d0c;color:#d97757;font-family:'JetBrains Mono',monospace;z-index:9999">
<svg viewBox="0 0 16 16" width="40" height="40" fill="none"><path d="M2 13 L6 6 L9 9 L14 3" stroke="#d97757" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
<div style="font-size:13px;letter-spacing:.18em">LOADING BULLVEDA · LIVE DATA</div>
<div style="font-size:11px;color:#5a6b63">connecting to market feed…</div></div>`;
body = body.replace(/<div id="root">\s*<\/div>/, `<div id="root">${LOADING}</div>`);

const outHtml = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>BullVeda — Terminal (bundled)</title>
${fonts}
<style>
${cssBlocks}
</style>
${cdn}
</head>
<body>${body}
<script>/* bullveda-boot.js (real-data sync adapter) */
${bootJs}
</script>
${jsBlocks}
</body>
</html>
`;

fs.writeFileSync(OUT, outHtml);
const kb = (Buffer.byteLength(outHtml) / 1024).toFixed(0);
console.log(`✓ bundled ${cssHrefs.length} CSS + ${nTx} JS modules → ${path.basename(OUT)} (${kb} KB, no in-browser Babel)`);
