# satellite-visuals

Visual assets for Earth-observation missions — stylised satellite vectors (SVG), rasters rendered from them, and (progressively) properly-licensed satellite photographs, mapped to CEOS MIM mission IDs via `index.json`.

## Naming convention

One folder per entity under `satellites/` (or `other-spacecraft/` for non-EO), all lowercase. Files inside use the folder name as their stem:

```
satellites/<name>/
  <name>.svg          colour vector (original work)
  <name>-icon.svg     monochrome icon vector (original work)
  <name>-1024px.png   render of <name>.svg (regenerate with tools/render_pngs.mjs)
  <name>-512px.png    render of <name>.svg
```

Lowercase matters: these paths are served from a case-sensitive Linux bind-mount.

## License

• Original materials — the SVGs, the rasters rendered from them, documentation, and curation/metadata authored by the maintainers — are licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

• Sourced photographs are added only under their owners' open licences, recorded per image in `index.json` and `ATTRIBUTIONS.csv`. See `ASSET-LICENSING.md` for the policy, including the attribution-is-not-a-licence rule.
