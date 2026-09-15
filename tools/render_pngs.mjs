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
// grey/<base>-grey-1024px.png and grey/<base>-grey-512px.png, and a sidecar
// grey/<base>-grey.render.json records the SHA-256 of the SVG rendered and of
// each PNG produced. check_index.py compares those hashes (never timestamps —
// a fresh clone gets whatever mtimes Git hands out), so a grey SVG regenerated
// without a re-render, or a PNG edited by hand, fails the gate. Run this after
// the desaturation tool.

import { Resvg } from "@resvg/resvg-js";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const RESVG_VERSION = require("@resvg/resvg-js/package.json").version;
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

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
      const svgBytes = readFileSync(join(svgDir, svgName));
      const svg = svgBytes.toString("utf8");
      const renders = {};
      let failed = false;
      for (const width of WIDTHS) {
        try {
          const resvg = new Resvg(svg, { fitTo: { mode: "width", value: width } });
          const png = resvg.render().asPng();
          const pngName = `${base}-${width}px.png`;
          writeFileSync(join(svgDir, pngName), png);
          renders[pngName] = sha256(png);
          rendered++;
        } catch (err) {
          failed = true;
          problems.push(`${group}/${folder}/${svgName} @${width}px: ${err.message}`);
        }
      }
      // Provenance sidecar for grey twins only (the gate reads it there). A
      // failed render leaves no sidecar, so the gate reports the folder.
      if (svgDir !== dir && !failed) {
        const stamp = {
          source: relative(repoRoot, join(svgDir, svgName)),
          svg_sha256: sha256(svgBytes),
          renderer: `@resvg/resvg-js ${RESVG_VERSION}`,
          renders,
        };
        writeFileSync(join(svgDir, `${base}.render.json`), JSON.stringify(stamp, null, 2) + "\n");
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
