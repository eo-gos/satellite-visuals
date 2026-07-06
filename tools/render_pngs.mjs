#!/usr/bin/env node
// Regenerate the 1024px/512px PNG rasters from the repo's own SVGs.
//
// The committed PNGs must always be renders of our CC BY 4.0 vector work,
// never third-party images — see ASSET-LICENSING.md. Run this after adding
// or editing any satellite/agency SVG:
//
//   cd tools && npm install && node render_pngs.mjs
//
// For each entity folder (satellites/*, other-spacecraft/*) the colour SVG
// (the .svg that is not *-icon.svg) is rendered to <base>-1024px.png and
// <base>-512px.png alongside it, where <base> is the SVG filename stem.

import { Resvg } from "@resvg/resvg-js";
import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const GROUPS = ["satellites", "other-spacecraft"];
const WIDTHS = [1024, 512];

let rendered = 0;
const problems = [];

for (const group of GROUPS) {
  const groupDir = join(repoRoot, group);
  let folders;
  try {
    folders = readdirSync(groupDir).filter((f) => statSync(join(groupDir, f)).isDirectory());
  } catch {
    continue;
  }

  for (const folder of folders) {
    const dir = join(groupDir, folder);
    const svgs = readdirSync(dir).filter(
      (f) => f.endsWith(".svg") && !f.endsWith("-icon.svg") && !f.includes("vectorizer"),
    );
    if (svgs.length === 0) {
      problems.push(`${group}/${folder}: no colour SVG found`);
      continue;
    }
    if (svgs.length > 1) {
      problems.push(`${group}/${folder}: multiple colour SVGs (${svgs.join(", ")}) — using ${svgs[0]}`);
    }

    const svgName = svgs[0];
    const base = svgName.replace(/\.svg$/, "");
    const svg = readFileSync(join(dir, svgName), "utf8");

    for (const width of WIDTHS) {
      try {
        const resvg = new Resvg(svg, { fitTo: { mode: "width", value: width } });
        writeFileSync(join(dir, `${base}-${width}px.png`), resvg.render().asPng());
        rendered++;
      } catch (err) {
        problems.push(`${group}/${folder}/${svgName} @${width}px: ${err.message}`);
      }
    }
  }
}

console.log(`Rendered ${rendered} PNGs.`);
if (problems.length) {
  console.log(`\n${problems.length} problem(s):`);
  for (const p of problems) console.log(`  - ${p}`);
  process.exitCode = 1;
}
