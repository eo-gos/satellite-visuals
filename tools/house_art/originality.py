"""Originality scoring for the house-artwork lane. Pillow only, no numpy.

Golden rule 6 refuses a 1:1 trace of one specific render. Route (b) makes a
trace impossible by construction — the drawing code never opens a reference —
but the repository should still be able to *show* that, so this compares an edge
map of our render against an edge map of each reference at matched scale.

**The raw score on its own is close to meaningless, and reporting it alone would
be misleading.** Two spacecraft drawings share "central body plus wings" edge
structure whatever their provenance. Measured across a 20-target batch, our
drawings scored a mean 0.20 against their OWN references and a mean 0.19 against
UNRELATED spacecraft's references: statistically the same distribution.

So every score is reported against a control: the same drawing scored the same
way against every other mission's references. What matters is the margin over
that control's 95th percentile. A drawing that scores no higher against its own
references than against strangers' is, by this measure, not copying anything.

    score      max edge overlap against this mission's own references
    control    the same drawing against every other mission's references
    margin     score - control_p95      <- this is the number to read
"""

import math

from PIL import Image, ImageChops, ImageFilter

SIZE = 256
SHIFT = 14          # translation search, to be fair about framing
STEP = 2
EDGE_PCT = 88       # keep the strongest 12% of gradient pixels

# Absolute floors, kept as a backstop for the degenerate case where the control
# set is tiny or absent.
FLAG = 0.45
FAIL = 0.60
# Margins over the control distribution. These are what normally decide.
MARGIN_REVIEW = 0.12
MARGIN_FAIL = 0.25


def _load_gray(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    return im.convert("L")


def _letterbox(im, size=SIZE):
    im = im.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("L", (size, size), 255)
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


def _percentile(hist, pct):
    total = sum(hist)
    if not total:
        return 0
    want = total * pct / 100.0
    run = 0
    for value, count in enumerate(hist):
        run += count
        if run >= want:
            return value
    return 255


def edges(gray):
    """Binary edge mask, mode '1'."""
    mag = gray.filter(ImageFilter.FIND_EDGES)
    thresh = max(_percentile(mag.histogram(), EDGE_PCT), 1)
    return mag.point(lambda v: 255 if v > thresh else 0).convert("1")


def edge_map(path):
    return edges(_letterbox(_load_gray(path)))


def _count(mask):
    return mask.histogram()[255]


def overlap(a, b, shift=SHIFT, step=STEP):
    """Cosine similarity of two binary edge masks over a translation search."""
    na, nb = _count(a), _count(b)
    if na < 1 or nb < 1:
        return 0.0, (0, 0)
    denom = math.sqrt(na * nb)
    best, best_off = 0.0, (0, 0)
    for dy in range(-shift, shift + 1, step):
        for dx in range(-shift, shift + 1, step):
            shifted = ImageChops.offset(b, dx, dy)
            value = _count(ImageChops.logical_and(a, shifted)) / denom
            if value > best:
                best, best_off = value, (dx, dy)
    return best, best_off


def _p95(values):
    if not values:
        return None
    ordered = sorted(values)
    idx = min(int(round(0.95 * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[idx]


def score(render_png, own_reference_pngs, control_reference_pngs=()):
    """Score one drawing. Returns a dict ready to store as originality.json."""
    ours = edge_map(render_png)

    rows = []
    for path in own_reference_pngs:
        try:
            ref = edge_map(path)
        except Exception as exc:                       # unreadable reference
            rows.append({"reference": str(path), "error": str(exc)})
            continue
        value, off = overlap(ours, ref)
        rows.append({"reference": str(path), "edge_overlap": round(value, 4),
                     "best_offset_px": list(off)})

    control = []
    for path in control_reference_pngs:
        try:
            control.append(overlap(ours, edge_map(path))[0])
        except Exception:
            continue
    ctrl_p95 = _p95(control)
    ctrl_mean = (sum(control) / len(control)) if control else None

    review_at = max(FLAG, (ctrl_p95 or 0.0) + MARGIN_REVIEW)
    fail_at = max(FAIL, (ctrl_p95 or 0.0) + MARGIN_FAIL)
    for row in rows:
        if "edge_overlap" in row:
            row["verdict"] = ("FAIL-probable-trace" if row["edge_overlap"] >= fail_at
                              else "review" if row["edge_overlap"] >= review_at
                              else "clear")

    scored = [r for r in rows if "edge_overlap" in r]
    top = max(scored, key=lambda r: r["edge_overlap"], default=None)
    best = top["edge_overlap"] if top else 0.0

    return {
        "method": ("Edge maps of our render and of each reference, both letterboxed "
                   f"to {SIZE} px, binarised at the {EDGE_PCT}th percentile of "
                   f"gradient magnitude, compared by cosine overlap over a "
                   f"+/-{SHIFT} px translation search."),
        "score_meaning": ("A raw overlap means little on its own: any two spacecraft "
                          "drawings share body-plus-wings edge structure. Read the "
                          "margin over the control p95, not the raw score."),
        "max_edge_overlap": round(best, 4),
        "closest_reference": top["reference"] if top else None,
        "control": {"n": len(control),
                    "mean": round(ctrl_mean, 4) if control else None,
                    "p95": round(ctrl_p95, 4) if control else None,
                    "note": "this drawing scored the same way against every OTHER "
                            "mission's references"},
        "thresholds": {"review_at": round(review_at, 4), "fail_at": round(fail_at, 4)},
        "margin_over_control_p95": (round(best - ctrl_p95, 4)
                                    if ctrl_p95 is not None else None),
        "overall": ("FAIL" if best >= fail_at else
                    "REVIEW" if best >= review_at else "PASS"),
        "per_reference": rows,
    }


def overlay(render_png, reference_png, out_png):
    """A human-readable diff: our edges dark, the reference's warm, coincident
    edges magenta. This is what tells a reviewer whether a high score means
    'same spacecraft' or 'same picture'."""
    ours = edge_map(render_png)
    ref = edge_map(reference_png)
    _, (dx, dy) = overlap(ours, ref)
    ref = ImageChops.offset(ref, dx, dy)
    out = Image.new("RGB", ours.size, (255, 255, 255))
    px = out.load()
    a, b = ours.load(), ref.load()
    for y in range(ours.size[1]):
        for x in range(ours.size[0]):
            if a[x, y] and b[x, y]:
                px[x, y] = (150, 40, 160)
            elif b[x, y]:
                px[x, y] = (214, 96, 60)
            elif a[x, y]:
                px[x, y] = (34, 40, 44)
    out.resize((ours.size[0] * 2, ours.size[1] * 2), Image.NEAREST).save(out_png)
    return out_png
