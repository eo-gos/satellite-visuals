"""House-artwork lane: original spacecraft drawings written from a description.

This package is the tooling for golden rule 6's "original depiction" lane. It
exists for folders that can never have a licensed photograph — the
derivative-refused owners (Roskosmos, CNSA, CMA, NSOAS, GHGSat) — and for icons
on folders whose photo licence forbids deriving one (every ESA Standard Licence
photo).

    description.json  ->  kit  ->  <folder>.svg  +  <folder>-icon.svg
         |                 ^
         |                 |
    reference URLs    checks: description<->drawing, projected geometry
    (never files)     originality: edge margin over a control distribution

Read `TASKING.md`, section "House artwork lane (generated)", before using it.
The short version: a photograph may be looked at, never traced, and never
stored here.

Modules
    kit          primitives, camera, flat shading, SVG writer, icon deriver
    schema       description.json contract and validator
    checks       description<->drawing consistency, projected-geometry checks
    originality  edge-overlap margin against a control distribution
    refs         reference gathering into a gitignored working directory
"""

from . import checks, kit, originality, refs, schema  # noqa: F401

__all__ = ["kit", "schema", "checks", "originality", "refs"]
