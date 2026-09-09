#!/usr/bin/env python3
"""Derive a mono silhouette icon from a photo cutout's alpha mask.

    python3 tools/make_icon.py goes-16 --out-dir tools/out/icons   # try one
    python3 tools/make_icon.py --all                               # in place
    python3 tools/make_icon.py --all --dry-run                     # gate report

Before the photo-only lane every folder had a hand-drawn house SVG, and the
icon was drawn from it. A folder whose only asset is a licensed photo has no
SVG to draw from, so the icon comes from the cutout instead: threshold the
cutout's alpha, trace the outline, emit one `<path style="fill:currentColor">`
with the viewBox fitted to the shape. That matches the existing icons, which is
what the portal's MissionIcon needs — it paints the file as a CSS mask filled
with currentColor, so only the shape matters, not the colour.

**Licence gate.** An icon is a *new published derivative*, so it needs a
stronger warrant than a cutout: `licenses.permits_icon_derivation()` allows
public domain and adaptation-permitting CC only, and refuses everything else —
notably every ESA Standard Licence photo (ESA refused background removal in
writing) and any media-terms or unrecognised licence. A refused folder is
skipped with a reason; it keeps its photo and simply has no icon. There is no
override flag, deliberately.

**Paperwork.** Each generated icon gets an ATTRIBUTIONS.csv row recording the
source file, the method and the licence deed — the same shape as the cutout
rows, because it is the same kind of thing: a mechanical derivative that
inherits the source licence.

Tracing uses `potracer`, a pure-Python potrace port (tools/requirements.txt) —
no system package, so the venv is the whole dependency.

Existing icons are never overwritten unless --force is given: the hand-drawn
ones are original artwork and outrank anything traced.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from licenses import deed_url, permits_icon_derivation  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# Working resolution for the trace. The mask is scaled so its long edge is this
# many units before tracing: big enough to keep the outline faithful, small
# enough that the emitted path stays a few kB rather than a few hundred.
TRACE_LONG_EDGE = 512
ALPHA_THRESHOLD = 128       # alpha >= this counts as "spacecraft"
COORD_DP = 1                # decimal places in the emitted path data


def _load_mask(png_path):
    """Alpha channel of the cutout as a boolean array, cropped to its bounding
    box and scaled so the long edge is TRACE_LONG_EDGE."""
    import numpy as np
    from PIL import Image

    im = Image.open(png_path)
    if im.mode not in ("RGBA", "LA"):
        raise ValueError(f"{png_path.name} has no alpha channel — not a cutout")
    alpha = im.convert("RGBA").split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError(f"{png_path.name} is fully transparent")
    alpha = alpha.crop(bbox)
    w, h = alpha.size
    scale = TRACE_LONG_EDGE / max(w, h)
    if scale < 1:
        alpha = alpha.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                             Image.LANCZOS)
    return np.asarray(alpha) >= ALPHA_THRESHOLD


def _trace(mask):
    """Bitmap -> (path data string, width, height)."""
    import potrace

    h, w = mask.shape
    # turdsize drops speckles: anything under ~0.04% of the frame is matting
    # noise, not a solar panel.
    turd = max(2, int(w * h * 0.0004))
    # potracer treats *falsy* cells as the shape, so a mask where True means
    # "spacecraft" has to go in inverted. Passed the right way up it traces the
    # background and the icon comes out as a negative.
    path = potrace.Bitmap(~mask).trace(turdsize=turd, alphamax=1.0,
                                       opticurve=True, opttolerance=0.4)
    n = COORD_DP

    def pt(p):
        return f"{round(p.x, n)},{round(p.y, n)}"

    parts = []
    for curve in path:
        parts.append(f"M{pt(curve.start_point)}")
        for seg in curve:
            if seg.is_corner:
                parts.append(f"L{pt(seg.c)}L{pt(seg.end_point)}")
            else:
                parts.append(f"C{pt(seg.c1)} {pt(seg.c2)} {pt(seg.end_point)}")
        parts.append("Z")
    return "".join(parts), w, h


def build_svg(png_path, title):
    data, w, h = _trace(_load_mask(png_path))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f'  <title>{title}</title>\n'
        f'  <path style="fill:currentColor" fill-rule="evenodd" d="{data}"/>\n'
        '</svg>\n'
    ), (w, h)


def source_cut(folder_dir, folder):
    """The cutout an icon is derived from — the 1024px one when it exists, else
    the 512px. Clean renders are never a source: they are published as-is by
    the rights holder, carry no alpha, and their licence refuses derivatives."""
    for size in (1024, 512):
        p = folder_dir / f"{folder}-photo-cut-{size}px.png"
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="*", help="folders to derive an icon for")
    ap.add_argument("--all", action="store_true",
                    help="every folder that has a cutout and no icon")
    ap.add_argument("--out-dir", help="write SVGs here instead of into the repo "
                                      "(no ATTRIBUTIONS row written)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing icon (hand-drawn icons outrank traced ones)")
    ap.add_argument("--dry-run", action="store_true", help="report the gate, write nothing")
    args = ap.parse_args()

    index = json.load(open(REPO / "index.json"))
    by_folder = {e.get("folder") or e["SVGColourPath"].split("/")[1]: e for e in index}

    if args.all:
        targets = sorted(by_folder)
    elif args.folders:
        targets = args.folders
    else:
        ap.error("name folders, or pass --all")

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    rows, made, skipped = [], 0, 0
    for folder in targets:
        entry = by_folder.get(folder)
        if entry is None:
            print(f"SKIP {folder}: no index.json entry")
            skipped += 1
            continue
        folder_dir = REPO / "satellites" / folder
        cut = source_cut(folder_dir, folder)
        if cut is None:
            if not args.all:
                print(f"SKIP {folder}: no -photo-cut-*px.png to derive from")
                skipped += 1
            continue
        icon_path = (out_dir / f"{folder}-icon.svg") if out_dir \
            else folder_dir / f"{folder}-icon.svg"
        if icon_path.exists() and not args.force:
            if not args.all:
                print(f"SKIP {folder}: {icon_path.name} exists (hand-drawn icons win; "
                      f"--force to overwrite)")
                skipped += 1
            continue
        licence = entry.get("imageLicense", "")
        if not permits_icon_derivation(licence):
            print(f"SKIP {folder}: licence {licence!r} does not permit deriving a "
                  f"published icon — folder keeps its photo, no icon")
            skipped += 1
            continue

        if args.dry_run:
            print(f"OK   {folder}: would trace {cut.name} -> {icon_path.name} ({licence})")
            made += 1
            continue

        svg, (w, h) = build_svg(cut, f"{folder} icon")
        icon_path.write_text(svg)
        print(f"OK   {folder}: {cut.name} -> {icon_path.name} "
              f"({w}x{h}, {len(svg) // 1024 or 1} kB)")
        made += 1
        if not out_dir:
            rel = f"satellites/{folder}/{folder}-icon.svg"
            deed = deed_url(licence)
            note = (f"silhouette derived from {cut.name} — alpha mask thresholded at "
                    f"{ALPHA_THRESHOLD}/255, outline traced with potracer "
                    f"(tools/make_icon.py); no new rights added, source licence flows "
                    f"through" + (f"; licence deed: {deed}" if deed else ""))
            rows.append([rel, entry.get("imageCredit") or entry.get("imageRightsHolder", ""),
                         entry.get("imageRightsHolder", ""),
                         entry.get("imageSourceURL", ""), licence, note])

    if rows:
        existing = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
        header, body = existing[0], existing[1:]
        by_path = {r[0]: r for r in body}
        for row in rows:
            if row[0] in by_path:
                by_path[row[0]][:] = row
            else:
                body.append(row)
        body.sort(key=lambda r: r[0])
        with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(body)
        print(f"\n{len(rows)} ATTRIBUTIONS.csv row(s) written.")

    print(f"\n{made} icon(s), {skipped} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
