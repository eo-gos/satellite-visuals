"""Primitive kit for the house-artwork lane: geometry in, house-style SVG out.

**This is the enforcement point for golden rule 6.** The SVG is WRITTEN from a
structured description of the spacecraft. Nothing in this module reads, samples,
traces or vectorises a raster image, and there is no code path by which one
could: the only inputs are numbers from `description.json`. Photographs are used
by the person writing that description, to know what the spacecraft looks like;
they never reach the drawing. That is what makes the output our own copyright
rather than a derivative of one particular render.

Every polygon comes from a 3D primitive (box, chamfered prism, plate, solar
wing, tube, tapered frustum, disc, dish, ribbed reflector, strut, detail plate)
positioned from the description, then projected with an orthographic camera and
flat-shaded from a fixed light direction into four tonal steps.

The mono icon is derived from OUR OWN colour geometry: the same structural
polygons re-emitted in a single currentColor fill, which is the union silhouette
of our own shapes. It is never traced from a photograph — the photo-derived icon
lane is `make_icon.py`, and it has its own, stricter licence gate.

Palette and detail level are calibrated to the repo's own exemplars (swot,
icesat, sentinel-1, jason-3, dscovr, saocom-1a).
"""

import math
from pathlib import Path

# ---------------------------------------------------------------- palette ----
# 10-colour house palette, sampled from the repo's own exemplar SVGs (swot,
# icesat, sentinel-1, jason-3, dscovr, saocom-1a): muted and neutral, no
# saturated brights, four tonal steps per material so depth reads, with the
# deepest step shared across all materials so a drawing stays within ten
# colours. Six to ten colours is the house range.
PALETTE = {
    "dark":     "#171a1c",   # shared deepest step / apertures / seams
    "body_l":   "#cdcecb",   # light face, grey structure
    "body_m":   "#9ea19d",
    "body_d":   "#6d716f",
    "gold_l":   "#cbb075",   # MLI, olive-gold rather than brass
    "gold_m":   "#a68b3c",
    "gold_d":   "#6b5722",
    "panel_l":  "#8a90ae",   # solar cells
    "panel_m":  "#666a8e",
    "panel_d":  "#3f4468",
}

# four tonal steps; the fourth is the shared near-black
MATERIALS = {
    "white":  ("body_l", "body_m", "body_d", "dark"),
    "gold":   ("gold_l", "gold_m", "gold_d", "dark"),
    "panel":  ("panel_l", "panel_m", "panel_d", "dark"),
    "dark":   ("body_d", "dark", "dark", "dark"),
    "mesh":   ("gold_l", "gold_m", "gold_d", "dark"),
}

LIGHT = (0.45, -0.55, 0.70)

# Mirror-symmetric solar-cell marks are the default: with the asymmetric pattern
# a left/right pair of wings mirrors along with the geometry, and the two wings
# read as accidentally different from each other. Set False only to reproduce a
# drawing made before this default changed.
DEFAULT_SYM_MARKS = True


def _n(v):
    m = math.sqrt(sum(c * c for c in v)) or 1.0
    return tuple(c / m for c in v)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(*vs):
    return tuple(sum(v[i] for v in vs) for i in range(3))


def _mul(v, s):
    return (v[0] * s, v[1] * s, v[2] * s)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


# ----------------------------------------------------------------- camera ----
class Camera:
    def __init__(self, az=38.0, el=20.0):
        a, e = math.radians(az), math.radians(el)
        self.right = (math.cos(a), -math.sin(a), 0.0)
        self.up = (-math.sin(a) * math.sin(e), -math.cos(a) * math.sin(e), math.cos(e))
        self.fwd = (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))

    def project(self, p):
        return (_dot(p, self.right), -_dot(p, self.up))

    def depth(self, p):
        return _dot(p, self.fwd)


# ------------------------------------------------------------------ scene ----
class Face:
    __slots__ = ("pts", "mat", "struct", "shade", "bias", "element")

    def __init__(self, pts, mat, struct=True, shade=None, bias=0.0):
        self.pts = pts
        self.mat = mat
        self.struct = struct
        self.shade = shade      # force 0/1/2/3 (light..near-black) or a palette key
        self.bias = bias        # nudge depth sort
        self.element = None     # which described part this belongs to


class _Part:
    def __init__(self, scene, name):
        self.scene, self.name, self.prev = scene, name, None

    def __enter__(self):
        self.prev = self.scene._element
        self.scene._element = self.name
        return self.scene

    def __exit__(self, *a):
        self.scene._element = self.prev
        return False


class Scene:
    def __init__(self, cam=None):
        self.faces = []
        self.cam = cam or Camera()
        self._element = None

    def part(self, name):
        """Tag every face made inside this block with the description element it
        depicts. `checks.check_description` compares these tags against
        description.json, so a part drawn but never described, or described but
        never drawn, fails the build instead of shipping."""
        return _Part(self, name)

    def add(self, f):
        f.element = self._element
        self.faces.append(f)
        return f

    # ---- primitives -------------------------------------------------------
    def box(self, centre, size, mat, basis=None, struct=True, detail_faces=None):
        """Axis-aligned (or basis-rotated) cuboid. size = (sx, sy, sz) full extents."""
        u, v, w = basis or ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        def P(a, b, c):
            return _add(centre, _mul(u, a * hx), _mul(v, b * hy), _mul(w, c * hz))
        quads = [
            [P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1)],    # +u
            [P(-1, 1, -1), P(-1, -1, -1), P(-1, -1, 1), P(-1, 1, 1)],  # -u
            [P(-1, 1, -1), P(-1, 1, 1), P(1, 1, 1), P(1, 1, -1)],    # +v
            [P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1)],  # -v
            [P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)],    # +w
            [P(-1, -1, -1), P(-1, 1, -1), P(1, 1, -1), P(1, -1, -1)],  # -w
        ]
        out = []
        for q in quads:
            out.append(self.add(Face(q, mat, struct)))
        return out

    def prism(self, centre, size, mat, bevel=0.14, axis="z", struct=True):
        """Box with its four long edges chamfered flat. Straight edges only -
        this reduces boxiness without rounding anything off."""
        sx, sy, sz = size
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        bx, by = bevel * min(sx, sy) / 2 * 2, bevel * min(sx, sy) / 2 * 2
        if axis == "y":
            prof = [(hx, hz - by), (hx - bx, hz), (-hx + bx, hz), (-hx, hz - by),
                    (-hx, -hz + by), (-hx + bx, -hz), (hx - bx, -hz), (hx, -hz + by)]
            ring0 = [(p[0], -hy, p[1]) for p in prof]
            ring1 = [(p[0], hy, p[1]) for p in prof]
        else:
            prof = [(hx, hy - by), (hx - bx, hy), (-hx + bx, hy), (-hx, hy - by),
                    (-hx, -hy + by), (-hx + bx, -hy), (hx - bx, -hy), (hx, -hy + by)]
            ring0 = [(p[0], p[1], -hz) for p in prof]
            ring1 = [(p[0], p[1], hz) for p in prof]
        ring0 = [_add(centre, p) for p in ring0]
        ring1 = [_add(centre, p) for p in ring1]
        n = len(ring0)
        for i in range(n):
            j = (i + 1) % n
            self.add(Face([ring0[i], ring0[j], ring1[j], ring1[i]], mat, struct))
        self.add(Face(ring1, mat, struct))
        self.add(Face(list(reversed(ring0)), mat, struct))

    def frustum(self, p0, p1, r0, r1, mat="white", n=10, struct=True, caps=True):
        """Tapered cylinder - cones, horns, baffles and antenna bases."""
        axis = _n(_sub(p1, p0))
        ref = (0, 0, 1) if abs(_dot(axis, (0, 0, 1))) < 0.9 else (1, 0, 0)
        e1 = _n(_cross(axis, ref))
        e2 = _cross(axis, e1)
        ring0, ring1 = [], []
        for i in range(n):
            a = 2 * math.pi * i / n
            d = _add(_mul(e1, math.cos(a)), _mul(e2, math.sin(a)))
            ring0.append(_add(p0, _mul(d, r0)))
            ring1.append(_add(p1, _mul(d, r1)))
        for i in range(n):
            j = (i + 1) % n
            self.add(Face([ring0[i], ring0[j], ring1[j], ring1[i]], mat, struct))
        if caps:
            self.add(Face(ring1, mat, struct))
            self.add(Face(list(reversed(ring0)), mat, struct))

    def plate(self, origin, u, v, thick=0.02, mat="panel", struct=True):
        """Thin slab spanned by vectors u and v from origin."""
        w = _mul(_n(_cross(u, v)), thick)
        c = _add(origin, _mul(u, 0.5), _mul(v, 0.5))
        return self.box(c, (1, 1, 1), mat,
                        basis=(u, v, w), struct=struct)

    def wing(self, origin, u, v, mat="panel", cols=3, rows=1, thick=0.03,
             gap=0.012, struct=True, sym_marks=None):
        """Solar wing: one slab plus darker gap strips marking cell blocks."""
        self.plate(origin, u, v, thick, mat, struct)
        nrm = _n(_cross(u, v))
        lift = _mul(nrm, thick * 0.62)
        for i in range(1, cols):
            t = i / cols
            a = _add(origin, _mul(u, t - gap / 2), lift)
            self.add(Face([a, _add(a, _mul(u, gap)),
                           _add(a, _mul(u, gap), v), _add(a, v)],
                          mat, struct=False, shade=2))
        for j in range(1, rows):
            t = j / rows
            a = _add(origin, _mul(v, t - gap / 2), lift)
            self.add(Face([a, _add(a, _mul(v, gap)),
                           _add(a, _mul(v, gap), u), _add(a, u)],
                          mat, struct=False, shade=2))
        # small interconnect patches inside each cell block, as in the exemplars
        cw, ch = 1.0 / cols, 1.0 / rows
        # sym_marks: a pattern that is its own mirror image, so a left/right pair
        # of wings does not read as accidentally different (George, round 1: MTG-S1)
        sym = DEFAULT_SYM_MARKS if sym_marks is None else sym_marks
        pattern = (((0.37, 0.22, 0.26, 0.16), (0.37, 0.62, 0.26, 0.16)) if sym
                   else ((0.18, 0.24, 0.26, 0.16), (0.58, 0.56, 0.22, 0.18)))
        for i in range(cols):
            for j in range(rows):
                for (fa, fb, fw, fh) in pattern:
                    a = _add(origin, _mul(u, (i + fa) * cw), _mul(v, (j + fb) * ch), lift)
                    self.add(Face([a, _add(a, _mul(u, fw * cw)),
                                   _add(a, _mul(u, fw * cw), _mul(v, fh * ch)),
                                   _add(a, _mul(v, fh * ch))],
                                  mat, struct=False, shade=0))

    def tube(self, p0, p1, r, mat="white", n=10, struct=True, caps=True):
        axis = _n(_sub(p1, p0))
        ref = (0, 0, 1) if abs(_dot(axis, (0, 0, 1))) < 0.9 else (1, 0, 0)
        e1 = _n(_cross(axis, ref))
        e2 = _cross(axis, e1)
        ring0, ring1 = [], []
        for i in range(n):
            a = 2 * math.pi * i / n
            off = _add(_mul(e1, r * math.cos(a)), _mul(e2, r * math.sin(a)))
            ring0.append(_add(p0, off))
            ring1.append(_add(p1, off))
        for i in range(n):
            j = (i + 1) % n
            self.add(Face([ring0[i], ring0[j], ring1[j], ring1[i]], mat, struct))
        if caps:
            self.add(Face(ring1, mat, struct))
            self.add(Face(list(reversed(ring0)), mat, struct))

    def disc(self, centre, axis, r, mat="white", n=12, struct=True, shade=None):
        axis = _n(axis)
        ref = (0, 0, 1) if abs(_dot(axis, (0, 0, 1))) < 0.9 else (1, 0, 0)
        e1 = _n(_cross(axis, ref))
        e2 = _cross(axis, e1)
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            pts.append(_add(centre, _mul(e1, r * math.cos(a)), _mul(e2, r * math.sin(a))))
        return self.add(Face(pts, mat, struct, shade=shade))

    def dish(self, centre, axis, r, depth, mat="white", n=14, struct=True):
        """Shallow paraboloid: rim ring plus a concave front face."""
        axis = _n(axis)
        ref = (0, 0, 1) if abs(_dot(axis, (0, 0, 1))) < 0.9 else (1, 0, 0)
        e1 = _n(_cross(axis, ref))
        e2 = _cross(axis, e1)
        back = _add(centre, _mul(axis, -depth))
        rim = []
        for i in range(n):
            a = 2 * math.pi * i / n
            rim.append(_add(centre, _mul(e1, r * math.cos(a)), _mul(e2, r * math.sin(a))))
        for i in range(n):
            j = (i + 1) % n
            self.add(Face([back, rim[i], rim[j]], mat, struct))
        self.disc(_add(centre, _mul(axis, -depth * 0.30)), axis, r * 0.94,
                  mat, n, struct=False, shade=1)

    def ribbed_reflector(self, hub, axis, r, ribs=14, sag=0.22, mat="mesh",
                         overhang=0.16, struct=True, scallop=0.0, mast=0.0):
        """Umbrella-style deployable mesh reflector: radial ribs + gore membranes."""
        axis = _n(axis)
        ref = (0, 0, 1) if abs(_dot(axis, (0, 0, 1))) < 0.9 else (1, 0, 0)
        e1 = _n(_cross(axis, ref))
        e2 = _cross(axis, e1)
        tips, mids = [], []
        for i in range(ribs):
            a = 2 * math.pi * i / ribs
            d = _add(_mul(e1, math.cos(a)), _mul(e2, math.sin(a)))
            tips.append(_add(hub, _mul(d, r), _mul(axis, -sag * r)))
            mids.append(_add(hub, _mul(d, r * 0.55), _mul(axis, -sag * r * 0.36)))
        # alternating gore shades so the membrane reads as a faceted umbrella;
        # scallop pulls the gore edge in between rib tips, as the real mesh hangs
        for i in range(ribs):
            j = (i + 1) % ribs
            a = 2 * math.pi * (i + 0.5) / ribs
            d = _add(_mul(e1, math.cos(a)), _mul(e2, math.sin(a)))
            edge = _add(hub, _mul(d, r * (1 - scallop)),
                        _mul(axis, -sag * r * (1 - scallop * 0.5)))
            pts = ([hub, mids[i], tips[i], edge, tips[j], mids[j]] if scallop
                   else [hub, mids[i], tips[i], tips[j], mids[j]])
            self.add(Face(pts, mat, struct, shade=(0 if i % 2 == 0 else 1)))
        if mast:
            self.tube(_add(hub, _mul(axis, -0.02 * r)),
                      _add(hub, _mul(axis, mast * r)), r * 0.022, "dark",
                      n=5, struct=struct, caps=False)
        # Ribs sit on the BACK of the mesh, as on the real deployable reflector,
        # and the whole rib cone is offset by a constant along -axis. Round 2 put
        # only the rib root proud of the membrane, so near-side ribs drew over the
        # canopy while far-side ribs disappeared behind it and showed only their
        # overhang - George: "the umbrella spokes are on both sides of the canopy".
        # A constant offset makes all of them sort the same way, so the spokes read
        # consistently through the full 360.
        back = _mul(axis, -0.055 * r)
        for i in range(ribs):
            a = 2 * math.pi * i / ribs
            d = _add(_mul(e1, math.cos(a)), _mul(e2, math.sin(a)))
            far = _add(hub, _mul(d, r * (1 + overhang)),
                       _mul(axis, -sag * r * (1 + overhang)), back)
            self.tube(_add(hub, back), far, r * 0.016,
                      "dark", n=5, struct=struct, caps=False)

    def greeble(self, origin, u, v, cells, mat="white", shade=None, lift=0.02):
        """Small flat detail plates lying on a face; never structural."""
        nrm = _mul(_n(_cross(u, v)), lift)
        for (a, b, w, h) in cells:
            o = _add(origin, _mul(u, a), _mul(v, b), nrm)
            self.add(Face([o, _add(o, _mul(u, w)),
                           _add(o, _mul(u, w), _mul(v, h)), _add(o, _mul(v, h))],
                          mat, struct=False, shade=shade))

    def strut(self, p0, p1, w, mat="white", struct=True):
        self.tube(p0, p1, w, mat, n=4, struct=struct)


# ---------------------------------------------------------------- shading ----
def _normal(pts):
    # Newell's method — robust for non-planar-ish polygons
    nx = ny = nz = 0.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return _n((nx, ny, nz))


def _shade_index(f):
    if f.shade is not None:
        return f.shade
    b = abs(_dot(_normal(f.pts), _n(LIGHT)))
    return 0 if b > 0.72 else (1 if b > 0.42 else (2 if b > 0.16 else 3))


# ----------------------------------------------------------------- output ----
def _fit(scene, margin=10.0, width=512.0, max_h=512.0):
    pts = [scene.cam.project(p) for f in scene.faces for p in f.pts]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    s = min((width - 2 * margin) / max(bw, 1e-6), (max_h - 2 * margin) / max(bh, 1e-6))
    h = round(bh * s + 2 * margin)
    ox = (width - bw * s) / 2 - min(xs) * s
    oy = (h - bh * s) / 2 - min(ys) * s
    return s, ox, oy, h


def _path(pts, s, ox, oy, cam):
    d = []
    for i, p in enumerate(pts):
        x, y = cam.project(p)
        d.append(f"{'M' if i == 0 else 'L'} {x * s + ox:.2f} {y * s + oy:.2f}")
    return " ".join(d) + " Z"


def render(scene, out_svg, out_icon, margin=10.0):
    s, ox, oy, h = _fit(scene, margin)
    cam = scene.cam
    order = sorted(scene.faces,
                   key=lambda f: (sum(cam.depth(p) for p in f.pts) / len(f.pts)) + f.bias)

    head = (f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny" '
            f'viewBox="0.00 0.00 512.00 {h}.00" width="512.00" height="{h}.00">\n')

    # dark underlay: the union of our structural shapes, so any hairline between
    # two adjacent flat fills reads as a drawn edge rather than a white gap.
    body = [head]
    for f in order:
        if f.struct:
            body.append(f'<path fill="{PALETTE["dark"]}" d="{_path(f.pts, s, ox, oy, cam)}"/>\n')
    for f in order:
        idx = _shade_index(f)
        key = MATERIALS[f.mat][idx]
        body.append(f'<path fill="{PALETTE[key]}" d="{_path(f.pts, s, ox, oy, cam)}"/>\n')
    body.append('</svg>\n')
    Path(out_svg).write_text("".join(body), encoding="utf-8")

    icon = [head.replace("</svg>", "")]
    icon.append('<g>\n')
    for f in order:
        if not f.struct:
            continue
        icon.append(f'<path style="fill:currentColor" d="{_path(f.pts, s, ox, oy, cam)}"/>\n')
    icon.append('</g>\n</svg>\n')
    Path(out_icon).write_text("".join(icon), encoding="utf-8")

    colours = sorted({PALETTE[MATERIALS[f.mat][_shade_index(f)]] for f in scene.faces})
    return {"height": h, "faces": len(scene.faces),
            "structural_faces": sum(1 for f in scene.faces if f.struct),
            "colours": colours}
