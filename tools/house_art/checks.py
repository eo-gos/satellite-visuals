"""Build-time checks for the house-artwork lane. Pillow only, no numpy.

Both checks exist because a human reviewer caught the failure first, twice:

  1. A drawing shipped with an element that appeared in no reference and in no
     description. -> check_description(): every solid is tagged with the
     description element it depicts, and the two sets must match.

  2. A drawing had solar wings that were correct in 3D and invisible on screen,
     and a dish that was attached in 3D and read as floating. -> check_projection():
     assertions are evaluated on the 2D result, after occlusion, not on the model.

Run them from the build step and fail loudly. They are cheap: a few hundred
polygons rasterised at 320 px.
"""

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import kit
from .schema import element_names, omitted_names

RES = 320


# ------------------------------------------------------ description <-> svg --
def check_description(description, scene):
    """Every described element drawn, and nothing drawn that is not described."""
    promised = element_names(description)
    drawn = {f.element for f in scene.faces if f.element}
    omitted = omitted_names(description)

    missing = promised - drawn - omitted
    extra = drawn - promised - omitted
    untagged = sum(1 for f in scene.faces if not f.element and f.struct)

    problems = []
    if missing:
        problems.append(f"described but not drawn: {sorted(missing)}")
    if extra:
        problems.append(f"drawn but not described: {sorted(extra)} — either "
                        f"describe it, or remove it; an element with no "
                        f"description is an element with no evidence")
    if untagged:
        problems.append(f"{untagged} structural faces carry no element tag "
                        f"(wrap them in `with scene.part(...)`)")
    return {"check": "description<->svg", "ok": not problems,
            "promised": sorted(promised), "drawn": sorted(drawn),
            "problems": problems}


# ------------------------------------------------------- projected geometry --
def _transform(scene):
    scale, ox, oy, height = kit._fit(scene)
    k = RES / 512.0
    def tf(p):
        x, y = scene.cam.project(p)
        return (x * scale * k + ox * k, y * scale * k + oy * k)
    return tf, max(int(round(height * k)), 8)


def element_masks(scene):
    """Paint the scene in depth order into an element-id buffer, so each
    element's pixel count is what SURVIVES occlusion rather than what was drawn.

    Returns (masks, painted_pixels, size) where masks maps element name to a
    mode-"1" Image.
    """
    tf, hpx = _transform(scene)
    buf = Image.new("L", (RES, hpx), 0)
    draw = ImageDraw.Draw(buf)
    ids = {}
    order = sorted(scene.faces,
                   key=lambda f: (sum(scene.cam.depth(p) for p in f.pts)
                                  / len(f.pts)) + f.bias)
    for face in order:
        if not face.element:
            continue
        idx = ids.setdefault(face.element, len(ids) + 1)
        poly = [tf(p) for p in face.pts]
        if len(poly) >= 3:
            draw.polygon(poly, fill=idx)

    masks = {}
    for name, idx in ids.items():
        masks[name] = buf.point(lambda v, i=idx: 255 if v == i else 0).convert("1")
    painted = sum(buf.point(lambda v: 255 if v else 0).convert("1")
                  .histogram()[255:256] or [0])
    return masks, painted, (RES, hpx)


def _count(mask):
    return mask.histogram()[255]


def _touching(a, b, slack_px=3):
    """Do two masks touch, allowing a few pixels for a drawn seam?"""
    grown = b.convert("L").filter(ImageFilter.MaxFilter(2 * slack_px + 1)).convert("1")
    return _count(ImageChops.logical_and(a, grown)) > 0


def _screen_angle(tf, p0, p1):
    import math
    a, b = tf(tuple(p0)), tf(tuple(p1))
    # screen y grows downward; negate so the angle reads the way a person means it
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 180


def check_projection(scene, asserts):
    """Evaluate claims about the 2D result.

    Supported assertions:
      {"assert": "visible", "element": name, "min_frac": f, "min_px": n}
          the element must survive occlusion with real pixels
      {"assert": "touches", "elements": [a, b], "slack_px": k}
          the two must read as joined (masts, booms, arms)
      {"assert": "screen_angle", "p0": [...], "p1": [...],
       "expect_deg": d, "tol_deg": t}
          a 3D segment must project at a given angle, for a shape that depends
          on it (a right-angle boom elbow reading as a right angle)
    """
    masks, painted, _ = element_masks(scene)
    tf, _ = _transform(scene)
    total = painted or 1
    problems, report = [], []

    for a in asserts or []:
        kind = a.get("assert")
        if kind == "visible":
            name = a["element"]
            mask = masks.get(name)
            if mask is None:
                problems.append(f"{name}: not drawn at all")
                continue
            px = _count(mask)
            frac = px / total
            report.append(f"{name} visible {px}px ({frac * 100:.1f}% of drawing)")
            if frac < a.get("min_frac", 0.0) or px < a.get("min_px", 0):
                problems.append(f"{name}: only {px}px visible ({frac * 100:.1f}%), "
                                f"below the floor — it is drawn but does not read")
        elif kind == "touches":
            x, y = a["elements"]
            if x not in masks or y not in masks:
                problems.append(f"touches {x}/{y}: one of them is missing")
                continue
            ok = _touching(masks[x], masks[y], a.get("slack_px", 3))
            report.append(f"{x} touches {y}: {ok}")
            if not ok:
                problems.append(f"{x} reads as detached from {y} on screen")
        elif kind == "screen_angle":
            deg = _screen_angle(tf, a["p0"], a["p1"])
            want = a["expect_deg"] % 180
            tol = a.get("tol_deg", 8)
            off = min(abs(deg - want), 180 - abs(deg - want))
            report.append(f"segment projects at {deg:.1f} deg (want {want} +/-{tol})")
            if off > tol:
                problems.append(f"segment projects at {deg:.1f} deg, wanted "
                                f"{want} +/-{tol} — the shape will not read as intended")
        else:
            problems.append(f"unknown assertion {kind!r}")

    return {"check": "projected geometry", "ok": not problems,
            "asserts": len(asserts or []), "report": report, "problems": problems}


def icon_legibility(icon_svg_png, size=16, min_ink=0.09):
    """Does the silhouette survive at `size` px?

    Some spacecraft genuinely do not survive it — widely spaced arrays on booms
    break into separate blobs — and that is a property of the vehicle, not a
    defect in the drawing. The lane surfaces it as an explicit decision rather
    than shipping an illegible icon: see TASKING.md, "the 16 px icon question".
    """
    im = Image.open(icon_svg_png)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    im = im.convert("L")
    im.thumbnail((size, size), Image.LANCZOS)
    mask = im.point(lambda v: 255 if v < 170 else 0).convert("1")
    ink = _count(mask) / float(im.width * im.height)

    # count connected components without numpy
    px = mask.load()
    seen = set()
    parts = 0
    for y in range(im.height):
        for x in range(im.width):
            if px[x, y] and (x, y) not in seen:
                parts += 1
                stack = [(x, y)]
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            nx, ny = cx + dx, cy + dy
                            if (0 <= nx < im.width and 0 <= ny < im.height
                                    and px[nx, ny] and (nx, ny) not in seen):
                                seen.add((nx, ny))
                                stack.append((nx, ny))
    return {"size_px": size, "components": parts, "ink_frac": round(ink, 3),
            "legible": parts == 1 and ink >= min_ink}


def run_all(description, scene, asserts):
    a = check_description(description, scene)
    b = check_projection(scene, asserts)
    return {"ok": a["ok"] and b["ok"], "checks": [a, b]}
