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
//
// A folder may also carry a greyscale twin under grey/ (written by
// tools/desaturate_svg.py from the colour SVG). It is rendered the same way to
// grey/<base>-grey-1024px.png and grey/<base>-grey-512px.png. Run this after
// the desaturation tool; check_index.py flags a grey PNG older than its SVG.

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
      // Photo-only lane: a folder with a licensed photo and no house artwork
      // is valid and has nothing to render here.
      continue;
    }
    if (svgs.length > 1) {
      problems.push(`${group}/${folder}: multiple colour SVGs (${svgs.join(", ")}) — using ${svgs[0]}`);
    }

    const jobs = [[dir, svgs[0]]];
    const greyDir = join(dir, "grey");
    let greySvgs = [];
    try {
      greySvgs = readdirSync(greyDir).filter((f) => f.endsWith("-grey.svg"));
    } catch {
      // no grey twin yet — fine, the colour render is all this folder has
    }
    if (greySvgs.length > 1) {
      problems.push(`${group}/${folder}/grey: multiple grey SVGs (${greySvgs.join(", ")}) — using ${greySvgs[0]}`);
    }
    if (greySvgs.length) jobs.push([greyDir, greySvgs[0]]);

    for (const [svgDir, svgName] of jobs) {
      const base = svgName.replace(/\.svg$/, "");
      const svg = readFileSync(join(svgDir, svgName), "utf8");
      for (const width of WIDTHS) {
        try {
          const resvg = new Resvg(svg, { fitTo: { mode: "width", value: width } });
          writeFileSync(join(svgDir, `${base}-${width}px.png`), resvg.render().asPng());
          rendered++;
        } catch (err) {
          problems.push(`${group}/${folder}/${svgName} @${width}px: ${err.message}`);
        }
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
