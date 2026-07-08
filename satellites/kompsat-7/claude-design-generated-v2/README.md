# kompsat-7 — Claude Design generated (v2)

Vectorized from the original `kompsat-7-1024px.png` per the workflow notes in PR #90.

## Files
- `kompsat-7.svg`        — colour SVG, 4-tone poster palette (slate panels, gold body, deep-shadow detail). Marching-squares trace, RDP-simplified, Catmull-Rom→Bezier smoothed. `fill-rule="evenodd"`.
- `kompsat-7-icon.svg`   — silhouette, single `<path fill="currentColor">`.
- `kompsat-7-1024px.png` — raster export of the colour SVG.
- `kompsat-7-512px.png`  — raster export of the colour SVG.

## Palette
- `#a8b3c4` light slate (panel)
- `#7a8499` mid slate (panel shadow / cell pattern)
- `#c9a340` gold (body)
- `#3d342a` deep shadow (camera optic, MLI texture)

## Pipeline
1. Per-pixel classify by hue + luma into 4 buckets.
2. Identify **panel regions** by morphologically closing the slate mask; reclassify gold pixels inside as panel-shadow (suppresses gold-cell pattern within solar panels).
3. Identify **body region** by closing the residual gold mask; reclassify stray slate pixels inside as gold (recovers body slats lit by camera flash).
4. Small dark shadow components → reabsorbed into neighbouring class.
5. Marching-squares contour trace at 512×463, RDP simplify (ε≈1.6 px), Catmull-Rom → cubic Bezier smoothing (tension 0.5).

## Known artefacts to clean in Inkscape
- Body retains some dark speckle from MLI texture — merge or simplify by hand if desired.
- One stubborn gold cell on the right panel survived the panel-region close (it was wider than the 7-px close kernel) — recolour to slate manually.
- Some jaggy edges where the panel meets the body — Path → Simplify in Inkscape will smooth these.
