#!/usr/bin/env python3
"""Derive the greyscale twin of every house colour SVG.

The colour drawing stays the master. This tool writes a sibling
``satellites/<folder>/grey/<folder>-grey.svg`` in which every colour is replaced
by its luminance grey, using the CSS ``filter: grayscale(1)`` weights
(0.2126 R + 0.7152 G + 0.0722 B on the sRGB values), so the committed twin
looks exactly like the filtered preview it was chosen from. Alpha is preserved.
Geometry is untouched: the twin is the same file with colours rewritten.

Why a subfolder rather than a ``-grey`` suffix beside the colour file: the API
resolves a folder's files by glob (``*.svg`` minus icons, ``*-512px.png`` minus
photo families) and takes the first match in sort order. A top-level
``<folder>-grey.svg`` sorts *ahead of* ``<folder>.svg``, so it would replace the
colour render in the API's slots the moment the repo was baked, with no code
change on either side. Files under ``grey/`` are invisible to that glob, so the
switch happens only when the API is told to look there (a separate PR).

Each twin carries a stamp comment naming the source file and the SHA-256 of the
colour SVG it was derived from. ``--check`` reads the stamp and fails when a
twin is missing, stale (source hash differs), or still carries chroma; it is
the freshness gate ``check_index.py`` calls, so an edited colour drawing cannot
ship with an old twin.

    python3 tools/desaturate_svg.py            # write/refresh every twin + index fields
    python3 tools/desaturate_svg.py swot smos  # only these folders
    python3 tools/desaturate_svg.py --check    # verify only, exit 1 on findings

PNG twins (``grey/<folder>-grey-1024px.png``, ``-512px.png``) are rendered from
the grey SVG by ``tools/render_pngs.mjs``; run it after this tool.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_utils import folder_of, load_index, save_index  # noqa: E402  (local sibling module)

REPO = Path(__file__).resolve().parent.parent
GREY_DIR = "grey"
STAMP_RE = re.compile(
    r"<!--\s*greyscale twin of (?P<src>\S+) sha256:(?P<sha>[0-9a-f]{64})\s*;[^>]*-->")

# Colour-bearing properties, as attributes (prop="…") or CSS declarations
# (prop:…) inside style="" and <style> blocks. `color` covers currentColor
# inheritance; the SVG paint servers are handled by their own tokens.
COLOUR_PROPS = r"fill|stroke|stop-color|flood-color|lighting-color|color"
TOKEN_RE = re.compile(
    r"(?P<prop>\b(?:" + COLOUR_PROPS + r"))"
    r"(?P<sep>\s*[:=]\s*\"?\s*)"
    r"(?P<val>#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|[a-zA-Z]+\b)",
)
# Keywords that are not colours, left alone.
NOT_COLOURS = {"none", "currentcolor", "inherit", "transparent", "url",
               "initial", "unset", "context-fill", "context-stroke"}
# Named colours seen in vector exports; anything else named is reported, not
# silently kept, so a chromatic keyword cannot slip through the chroma check.
NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "lime": (0, 255, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "yellow": (255, 255, 0), "cyan": (0, 255, 255), "aqua": (0, 255, 255),
    "magenta": (255, 0, 255), "fuchsia": (255, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192), "maroon": (128, 0, 0),
    "olive": (128, 128, 0), "navy": (0, 0, 128), "purple": (128, 0, 128),
    "teal": (0, 128, 128), "orange": (255, 165, 0), "gold": (255, 215, 0),
    "darkgray": (169, 169, 169), "darkgrey": (169, 169, 169),
    "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211),
    "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
}


class UnknownColour(ValueError):
    """A colour keyword this tool does not know: add it to NAMED deliberately."""


def luma(r, g, b):
    """CSS grayscale(1) luminance on sRGB-encoded channels, rounded to 0-255."""
    return max(0, min(255, round(0.2126 * r + 0.7152 * g + 0.0722 * b)))


def _parse_hex(token):
    h = token[1:]
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    alpha = h[6:8] if len(h) == 8 else ""
    return (r, g, b), alpha


def _parse_rgb(token):
    inner = token[token.index("(") + 1:token.rindex(")")]
    parts = [p.strip() for p in re.split(r"[,\s/]+", inner) if p.strip()]
    if len(parts) < 3:
        raise UnknownColour(token)
    chans = []
    for p in parts[:3]:
        chans.append(round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p)))
    alpha = parts[3] if len(parts) > 3 else None
    return tuple(chans), alpha


def grey_of(token):
    """The greyscale form of one colour token, or the token itself when it is
    not a colour (none, url(...), currentColor ...). Raises UnknownColour for a
    colour keyword outside NAMED."""
    low = token.lower()
    if low in NOT_COLOURS or low.startswith("url("):
        return token
    if token.startswith("#"):
        (r, g, b), alpha = _parse_hex(token)
        y = luma(r, g, b)
        return f"#{y:02x}{y:02x}{y:02x}{alpha.lower()}"
    if low.startswith("rgb"):
        (r, g, b), alpha = _parse_rgb(token)
        y = luma(r, g, b)
        return f"rgba({y},{y},{y},{alpha})" if alpha is not None else f"rgb({y},{y},{y})"
    if low in NAMED:
        y = luma(*NAMED[low])
        return f"#{y:02x}{y:02x}{y:02x}"
    raise UnknownColour(token)


def is_chromatic(token):
    """True when a token is a colour whose channels differ (i.e. not grey)."""
    low = token.lower()
    if low in NOT_COLOURS or low.startswith("url("):
        return False
    if token.startswith("#"):
        (r, g, b), _ = _parse_hex(token)
    elif low.startswith("rgb"):
        (r, g, b), _ = _parse_rgb(token)
    elif low in NAMED:
        r, g, b = NAMED[low]
    else:
        raise UnknownColour(token)
    return not (r == g == b)


def desaturate(svg_text):
    """Rewrite every colour token in an SVG document to its luminance grey."""
    def sub(m):
        try:
            return m.group("prop") + m.group("sep") + grey_of(m.group("val"))
        except UnknownColour:
            raise UnknownColour(f"{m.group('prop')}: {m.group('val')!r}")
    return TOKEN_RE.sub(sub, svg_text)


def chromatic_tokens(svg_text):
    """Every colour token in the document that still carries chroma."""
    found = []
    for m in TOKEN_RE.finditer(svg_text):
        val = m.group("val")
        try:
            if is_chromatic(val):
                found.append(val)
        except UnknownColour:
            found.append(val)
    return found


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(rel_source, sha):
    return (f"<!-- greyscale twin of {rel_source} sha256:{sha}; generated by "
            f"tools/desaturate_svg.py, do not edit: regenerate -->")


def read_stamp(grey_text):
    m = STAMP_RE.search(grey_text)
    return (m.group("src"), m.group("sha")) if m else (None, None)


def twin_paths(folder):
    """Repo-relative paths of the grey SVG and its two PNG renders."""
    base = f"satellites/{folder}/{GREY_DIR}/{folder}-grey"
    return {"SVGGreyPath": f"{base}.svg",
            "PNGGrey1024Path": f"{base}-1024px.png",
            "PNGGrey512Path": f"{base}-512px.png"}


def write_twin(entry, repo=REPO):
    """Write the grey SVG for one entry and return the three index fields."""
    folder = folder_of(entry)
    src_rel = entry["SVGColourPath"]
    src = repo / src_rel
    text = src.read_text(encoding="utf-8")
    grey = desaturate(text)
    # Stamp right after the root <svg …> start tag, so the XML declaration and
    # any DOCTYPE stay first.
    m = re.search(r"<svg\b[^>]*>", grey)
    if not m:
        raise ValueError(f"{src_rel}: no <svg> root element")
    grey = grey[:m.end()] + "\n" + stamp(src_rel, sha256_of(src)) + grey[m.end():]
    paths = twin_paths(folder)
    out = repo / paths["SVGGreyPath"]
    out.parent.mkdir(parents=True, exist_ok=True)
    # Idempotent: an unchanged twin is not rewritten, so its mtime stays older
    # than the PNGs rendered from it and the freshness check stays quiet.
    if not (out.is_file() and out.read_text(encoding="utf-8") == grey):
        out.write_text(grey, encoding="utf-8")
    return paths


def check_entry(entry, repo=REPO):
    """Findings for one entry's grey twin: [] when present, fresh and grey.
    Entries without a colour SVG (photo-only folders) have nothing to check."""
    folder = folder_of(entry)
    src_rel = entry.get("SVGColourPath")
    if not src_rel:
        return []
    problems = []
    expected = twin_paths(folder)
    for field, rel in expected.items():
        if entry.get(field) != rel:
            problems.append(f"{folder}: {field} should be {rel!r}, found "
                            f"{entry.get(field)!r}")
        if not (repo / rel).is_file():
            problems.append(f"{folder}: missing {rel} — run tools/desaturate_svg.py"
                            + ("" if rel.endswith(".svg") else " then tools/render_pngs.mjs"))
    grey_path = repo / expected["SVGGreyPath"]
    if grey_path.is_file():
        grey_text = grey_path.read_text(encoding="utf-8")
        src, sha = read_stamp(grey_text)
        if sha is None:
            problems.append(f"{folder}: grey twin has no source stamp — regenerate")
        else:
            if src != src_rel:
                problems.append(f"{folder}: grey twin stamped from {src!r}, entry "
                                f"names {src_rel!r}")
            if (repo / src_rel).is_file() and sha != sha256_of(repo / src_rel):
                problems.append(f"{folder}: grey twin is stale — colour SVG changed "
                                f"since it was derived; run tools/desaturate_svg.py")
        chroma = chromatic_tokens(grey_text)
        if chroma:
            problems.append(f"{folder}: grey twin still carries colour: "
                            f"{sorted(set(chroma))[:5]}")
        src_png = repo / expected["SVGGreyPath"]
        for field in ("PNGGrey1024Path", "PNGGrey512Path"):
            png = repo / expected[field]
            if png.is_file() and png.stat().st_mtime < src_png.stat().st_mtime:
                problems.append(f"{folder}: {expected[field]} is older than the grey "
                                f"SVG — run tools/render_pngs.mjs")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folders", nargs="*", help="only these folders (default: all with a colour SVG)")
    ap.add_argument("--check", action="store_true", help="verify twins only; exit 1 on findings")
    args = ap.parse_args(argv)

    entries = load_index(REPO)
    wanted = set(args.folders)
    targets = [e for e in entries
               if e.get("SVGColourPath") and (not wanted or folder_of(e) in wanted)]
    missing = wanted - {folder_of(e) for e in targets}
    if missing:
        print(f"FAIL unknown folder(s) or no colour SVG: {sorted(missing)}")
        return 2

    if args.check:
        problems = [p for e in targets for p in check_entry(e)]
        for p in problems:
            print(f"FAIL {p}")
        if not problems:
            print(f"OK   {len(targets)} grey twins present, fresh and chroma-free")
        return 1 if problems else 0

    written = 0
    # Photo-only entries carry the grey fields as "" like every other path
    # field, so the index keeps one shape.
    for e in entries:
        if not e.get("SVGColourPath"):
            for field in twin_paths("x"):
                e.setdefault(field, "")
    for e in targets:
        try:
            paths = write_twin(e)
        except UnknownColour as exc:
            print(f"FAIL {folder_of(e)}: unknown colour keyword {exc} — add it to NAMED")
            return 1
        e.update(paths)
        written += 1
    save_index(entries, REPO)
    print(f"Wrote {written} grey twin(s); index fields updated. "
          f"Now render the PNGs: cd tools && node render_pngs.mjs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
