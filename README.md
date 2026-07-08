# satellite-visuals

Visual assets for Earth-observation missions — stylised satellite vectors (SVG), rasters rendered from them, and (progressively) properly-licensed satellite photographs, mapped to CEOS MIM mission IDs via `index.json`.

## Naming convention

One folder per entity under `satellites/` (or `other-spacecraft/` for non-EO), all lowercase. Files inside use the folder name as their stem:

```
satellites/<name>/
  <name>.svg                    colour vector (original work)
  <name>-icon.svg              monochrome icon vector (original work)
  <name>-1024px.png            render of <name>.svg (regenerate with tools/render_pngs.mjs)
  <name>-512px.png             render of <name>.svg
  <name>-photo.<ext>          raw sourced photo, bit-identical to source (evidence-grade)
  <name>-photo-cut-1024px.png  transparent cutout, natural aspect, max-dim 1024 (derived)
  <name>-photo-cut-512px.png   smaller cutout for cards (derived)
```

Lowercase matters: these paths are served from a case-sensitive Linux bind-mount.

## Deriving photo cutouts

Transparent cutouts (`-photo-cut-*.png`) are derived from raw `-photo.*` files by
`tools/process_photos.py`. When the raw carries its own alpha channel (many agency
renders ship pre-cut — 13 of the 22 batch-1 raws did), that alpha is used directly:
it is ground truth, and matting over it only loses structure (#115). Otherwise the
background is removed with rembg (default model `isnet-general-use`, which beat
u2net on thin structure in the batch-1 bake-off; `--model` overrides,
`--force-matting` disables the source-alpha preference) → alpha-bbox crop → size
set. The raw photo is never modified; the cutout is a mechanical derivative and the
source licence flows through unchanged (see `ASSET-LICENSING.md` and issue #109).

```bash
# one-off setup (venv — never install these globally)
python3 -m venv .venv && . .venv/bin/activate     # needs Python >= 3.10
pip install -r tools/requirements.txt              # rembg downloads a ~176 MB model on first run

# 1. PROCESS — derive cutouts + write cut_report.json (source sha, rembg version, bbox)
python3 tools/process_photos.py --all              # every index.json entry with a PhotoPath
python3 tools/process_photos.py ace cloudsat       # or named folders
#   --out-dir DIR   write cutouts + report elsewhere (dry runs — nothing lands in the tree)
#   --gallery       also emit cut_gallery.html
#   --margin 0.04   crop margin as a fraction of the cutout's larger side
#   --force         rebuild existing cutouts (otherwise idempotent — existing outputs skip)

# 2. GALLERY REVIEW — open cut_gallery.html, eyeball each before/after (cutout sits on a
#    checkerboard so transparency shows), approve/reject, then "Copy picks JSON".
#    Expected failure mode: thin booms/antennas and low-contrast bodies get eaten —
#    reject those for manual mask touch-up.

# 3. APPLY — copy approved cutouts into the tree and write the paperwork (inherited
#    ATTRIBUTIONS.csv rows inserted after each raw photo's row + PhotoCut1024Path /
#    PhotoCut512Path index fields). Idempotent; rejected folders are ignored.
python3 tools/apply_cuts.py --report cuts/cut_report.json \
    --picks picks.json --cuts-dir cuts --repo-root .
#    then: git diff, branch, commit, PR (the products PR is separate from tool changes)
```

Licences that do not permit derivatives (media-terms, ND) are skipped by default;
`--allow-nonderiv` overrides once permission is confirmed. `tools/licenses.py` maps
each licence name to its deed URL (the hyperlink target the portal credit line needs).

## License

• Original materials — the SVGs, the rasters rendered from them, documentation, and curation/metadata authored by the maintainers — are licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

• Sourced photographs are added only under their owners' open licences, recorded per image in `index.json` and `ATTRIBUTIONS.csv`. See `ASSET-LICENSING.md` for the policy, including the attribution-is-not-a-licence rule.
