#!/usr/bin/env python3
"""Derive transparent cutouts from raw satellite photos (issue #109).

Pipeline per mission folder:
    raw <folder>-photo.<ext>
      -> alpha: the source file's own channel when it carries one (many agency
         renders ship pre-cut — issue #115 showed matting a pre-cut raw only
         DEGRADES it), else background removal (rembg, local ONNX model;
         default isnet-general-use; --force-matting overrides the preference)
      -> crop to the alpha bounding box + a small margin
      -> emit <folder>-photo-cut-1024px.png and <folder>-photo-cut-512px.png
         (natural aspect, bound by max dimension, never padded square)

The raw photo is evidence-grade and is NEVER modified or moved — this tool only
reads it. Cutouts are mechanical derivatives; the source licence flows through
unchanged (see ASSET-LICENSING.md). Every run writes cut_report.json for the
paperwork step (ATTRIBUTIONS rows + index.json fields), recording the source
sha256, rembg version, alpha bbox and output paths.

    # process named folders in place (writes cutouts alongside the raw photo)
    python3 tools/process_photos.py ace cloudsat

    # process every folder whose index.json entry carries a PhotoPath
    python3 tools/process_photos.py --all

    # dry run: read a checkout that has the raw photos, write cutouts elsewhere
    python3 tools/process_photos.py --all --root ../batch01 --out-dir ../cutouts --gallery

Outputs are idempotent: an existing cutout whose recorded source sha matches is
skipped unless --force. Folders with no raw photo are skipped.

Requires tools/requirements.txt (rembg + Pillow). Use a venv:
    python3 -m venv .venv && . .venv/bin/activate && pip install -r tools/requirements.txt
"""

import argparse
import base64
import hashlib
import html
import io
import json
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from licenses import deed_url, permits_derivatives  # noqa: E402  (local sibling module)

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
GROUPS = ("satellites", "other-spacecraft")
RAW_EXTS = ("png", "jpg", "jpeg", "webp", "tif", "tiff", "gif")
DEFAULT_SIZES = (1024, 512)
DEFAULT_MARGIN = 0.04  # fraction of the cutout's larger side, added to every edge


def rembg_version():
    try:
        return version("rembg")
    except PackageNotFoundError:
        return "unknown"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_index(root):
    path = root / "index.json"
    if not path.exists():
        return [], {}
    index = json.load(open(path))
    by_folder = {}
    for e in index:
        colour = e.get("SVGColourPath", "")
        parts = colour.split("/")
        if len(parts) >= 2:
            by_folder[parts[1]] = e
    return index, by_folder


def group_of(folder, entry, root):
    """Which top-level group (satellites / other-spacecraft) a folder lives in."""
    if entry:
        parts = entry.get("SVGColourPath", "").split("/")
        if len(parts) >= 2:
            return parts[0]
    for g in GROUPS:
        if (root / g / folder).is_dir():
            return g
    return GROUPS[0]


def find_raw(root, group, folder, entry):
    """Locate the raw <folder>-photo.<ext>. Prefer the index PhotoPath; else glob."""
    if entry and entry.get("PhotoPath"):
        p = root / entry["PhotoPath"]
        if p.exists():
            return p
    for ext in RAW_EXTS:
        p = root / group / folder / f"{folder}-photo.{ext}"
        if p.exists():
            return p
    return None


MIN_SOURCE_ALPHA_TRANSPARENT = 0.05  # share of fully-clear pixels that marks a real cutout


def usable_source_alpha(rgba):
    """True when the raw already carries a real cutout alpha (13 of the 22
    batch-1 raws did — NASA renders ship pre-cut). 'Real' means a meaningful
    share of fully-transparent pixels; an all-opaque alpha channel is just
    format padding, and matting is still needed."""
    hist = rgba.getchannel("A").histogram()
    return hist[0] / (rgba.width * rgba.height) >= MIN_SOURCE_ALPHA_TRANSPARENT


def alpha_bbox_with_margin(img, margin):
    """Bounding box of non-transparent pixels, expanded by `margin` * max side
    on every edge, clamped to the image. Returns (raw_bbox, padded_bbox)."""
    alpha = img.getchannel("A")
    bbox = alpha.getbbox()  # (l, t, r, b) of non-zero alpha, or None if fully clear
    if bbox is None:
        return None, None
    l, t, r, b = bbox
    pad = round(margin * max(r - l, b - t))
    pl, pt = max(0, l - pad), max(0, t - pad)
    pr, pb = min(img.width, r + pad), min(img.height, b + pad)
    return bbox, (pl, pt, pr, pb)


def scaled_to_max(img, max_dim):
    """Resize so the larger side == max_dim. Never upscale — 'max-dimension
    bound' means an upper bound, so small cutouts stay native (upscaling a
    cutout only invents detail and bloats the file)."""
    longest = max(img.width, img.height)
    if longest <= max_dim:
        return img
    scale = max_dim / longest
    return img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.LANCZOS,
    )


def process_folder(folder, entry, root, out_base, get_session, model_name, sizes,
                   margin, force, allow_nonderiv=False, force_matting=False):
    group = group_of(folder, entry, root)
    raw = find_raw(root, group, folder, entry)
    if raw is None:
        print(f"SKIP {folder}: no raw <folder>-photo.<ext>")
        return None

    # Licence flow-down guard (ASSET-LICENSING.md / issue #109): media-terms and
    # ND photos grant use *as provided* — a cropped/bg-removed cutout may exceed
    # permission. The repo records these cases in imageStatus (media-terms /
    # trademark-editorial-use), not necessarily in imageLicense, so both fields
    # gate. Refuse to derive unless explicitly overridden.
    lic = entry.get("imageLicense", "") if entry else ""
    status = entry.get("imageStatus", "") if entry else ""
    guarded_status = status in ("media-terms", "trademark-editorial-use")
    guarded_licence = bool(lic) and not permits_derivatives(lic)
    if (guarded_status or guarded_licence) and not allow_nonderiv:
        reason = f"imageStatus '{status}'" if guarded_status else f"licence '{lic}'"
        print(f"SKIP {folder}: {reason} does not permit derivatives "
              f"(use --allow-nonderiv to override once permission is confirmed)")
        return {
            "folder": folder, "group": group,
            "source": str(raw.relative_to(root)) if _under(raw, root) else str(raw),
            "image_license": lic, "image_status": status,
            "status": "skipped-no-derivatives",
        }

    out_dir = out_base / group / folder
    out_paths = {size: out_dir / f"{folder}-photo-cut-{size}px.png" for size in sizes}
    src_sha = sha256_file(raw)

    if not force and all(p.exists() for p in out_paths.values()):
        print(f"skip {folder}: cutouts exist (use --force to rebuild)")
        return {
            "folder": folder, "group": group,
            "source": str(raw.relative_to(root)) if _under(raw, root) else str(raw),
            "source_sha256": src_sha, "status": "skipped-exists",
            "outputs": {str(s): _relout(p, out_base) for s, p in out_paths.items()},
        }

    base_rec = {
        "folder": folder, "group": group,
        "source": str(raw.relative_to(root)) if _under(raw, root) else str(raw),
        "source_abspath": str(raw),
        "source_sha256": src_sha,
    }

    t0 = time.perf_counter()
    try:
        with Image.open(raw) as im:
            src_w, src_h = im.size
            rgba = im.convert("RGBA")
    except Exception as exc:  # noqa: BLE001  (bad/mislabelled raster, decode error)
        print(f"FAIL {folder}: cannot load raw ({type(exc).__name__}: {exc})")
        return {**base_rec, "status": "failed-load", "error": f"{type(exc).__name__}: {exc}"}
    if not force_matting and usable_source_alpha(rgba):
        # the publisher already cut this one out — their alpha is ground truth,
        # and matting over it can only lose structure (issue #115)
        method = "source-alpha"
        cut = rgba
    else:
        method = "matting"
        from rembg import remove
        cut = remove(rgba, session=get_session())  # RGBA, bg alpha->0
    raw_bbox, bbox = alpha_bbox_with_margin(cut, margin)
    if bbox is None:
        print(f"FAIL {folder}: {method} produced a fully-transparent mask")
        return {**base_rec, "status": "failed-empty-mask", "method": method}
    cropped = cut.crop(bbox)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for size in sizes:
        img = scaled_to_max(cropped, size)
        img.save(out_paths[size], "PNG", optimize=True)
        written[str(size)] = {
            "path": _relout(out_paths[size], out_base),
            "width": img.width, "height": img.height,
        }
    dt = time.perf_counter() - t0

    dims = "/".join(f"{written[str(s)]['width']}x{written[str(s)]['height']}" for s in sizes)
    print(f"OK   {folder}: {src_w}x{src_h} -> {method} -> bbox {bbox} -> {dims}  ({dt:.1f}s)")

    entry = entry or {}
    rv = rembg_version()
    if method == "source-alpha":
        note = (f"derivative of {raw.name} — cropped; alpha taken from the source "
                f"file's own channel (tools/process_photos.py, no matting)")
    else:
        note = (f"derivative of {raw.name} — cropped, background removed "
                f"(tools/process_photos.py, rembg {rv} {model_name})")
    return {
        **base_rec,
        "source_size": [src_w, src_h],
        "method": method,
        "rembg_version": rv if method == "matting" else None,
        "rembg_model": model_name if method == "matting" else None,
        "margin": margin,
        "alpha_bbox": list(raw_bbox),
        "alpha_bbox_padded": list(bbox),
        "outputs": written,
        # licence + provenance carried through so the paperwork step (ATTRIBUTIONS
        # rows + index.json fields) needs no second lookup. Derived files inherit
        # these from the raw photo unchanged (mechanical derivative, no new rights).
        "image_license": lic,
        "license_deed_url": deed_url(lic),
        "image_rights_holder": entry.get("imageRightsHolder", ""),
        "image_source_url": entry.get("imageSourceURL", ""),
        "image_credit": entry.get("imageCredit", ""),
        "image_status": entry.get("imageStatus", ""),
        "derivative_note": note,
        "modified": True,
        "status": "ok",
        "seconds": round(dt, 2),
    }


def _under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _relout(path, out_base):
    return str(path.relative_to(out_base)) if _under(path, out_base) else str(path)


# --------------------------------------------------------------------------- #
# before/after approval gallery (same ergonomics as tools/make_gallery.py)
# --------------------------------------------------------------------------- #
def _thumb_data_uri(path, max_dim=360):
    with Image.open(path) as im:
        im = im.convert("RGBA")
        im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def build_gallery(report, root, out_base):
    """Self-contained before/after review page. Cutout thumbnails sit on a
    checkerboard so transparency is visible; per-item approve/reject radios and
    a 'copy picks JSON' button mirror tools/make_gallery.py."""
    cards = []
    for r in sorted(report["photos"], key=lambda x: x["folder"]):
        folder = r["folder"]
        if r["status"] not in ("ok", "skipped-exists"):
            cards.append(f"""
    <section data-key="{html.escape(folder)}" class="bad">
      <h2>{html.escape(folder)} <small>{html.escape(r['status'])}</small></h2>
      <p>Processing failed — no cutout to review.</p>
    </section>""")
            continue
        raw_abs = Path(r.get("source_abspath") or (root / r["source"]))
        # first declared output size = the largest cutout
        first = next(iter(r["outputs"].values()))
        cut_abs = out_base / first["path"]
        try:
            before = _thumb_data_uri(raw_abs)
            after = _thumb_data_uri(cut_abs)
        except Exception as exc:  # noqa: BLE001
            cards.append(f"""
    <section data-key="{html.escape(folder)}" class="bad">
      <h2>{html.escape(folder)}</h2><p>thumbnail error: {html.escape(str(exc))}</p>
    </section>""")
            continue
        lic = r.get("image_license") or "—"
        deed = r.get("license_deed_url") or ""
        lic_html = (f'<a href="{html.escape(deed)}" target="_blank">{html.escape(lic)}</a>'
                    if deed else html.escape(lic))
        cards.append(f"""
    <section data-key="{html.escape(folder)}">
      <h2>{html.escape(folder)}</h2>
      <div class="pair">
        <figure><figcaption>raw</figcaption><img src="{before}"></figure>
        <figure class="cut"><figcaption>cutout</figcaption><img src="{after}"></figure>
      </div>
      <div class="meta">licence: {lic_html} · {html.escape(r.get('method') or 'matting')} · bbox {html.escape(str(r.get('alpha_bbox_padded')))}</div>
      <div class="vote">
        <label class="approve"><input type="radio" name="{html.escape(folder)}" value="approve" checked> approve</label>
        <label class="reject"><input type="radio" name="{html.escape(folder)}" value="reject"> reject (manual touch-up)</label>
      </div>
    </section>""")

    page = f"""<!doctype html>
<meta charset="utf-8">
<title>satellite-visuals cutout review</title>
<style>
 body {{ font: 14px/1.4 system-ui; margin: 2rem; }}
 section {{ border-top: 1px solid #ccc; padding: 1rem 0; }}
 section.bad {{ background: #fff4f4; }}
 h2 {{ margin: 0 0 .5rem; }}
 h2 small {{ color: #b00; font-weight: 400; }}
 .pair {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
 figure {{ margin: 0; }}
 figcaption {{ font-size: 12px; color: #666; margin-bottom: 4px; }}
 figure img {{ max-width: 360px; max-height: 360px; display: block; border: 1px solid #ddd; }}
 figure.cut img {{
   background-color: #fff;
   background-image:
     linear-gradient(45deg,#ccc 25%,transparent 25%),
     linear-gradient(-45deg,#ccc 25%,transparent 25%),
     linear-gradient(45deg,transparent 75%,#ccc 75%),
     linear-gradient(-45deg,transparent 75%,#ccc 75%);
   background-size: 20px 20px;
   background-position: 0 0, 0 10px, 10px -10px, -10px 0;
 }}
 .meta {{ color: #555; margin: .4rem 0; }}
 .vote label {{ margin-right: 1rem; cursor: pointer; }}
 section:has(.reject input:checked) {{ background: #fff4f4; }}
 #bar {{ position: fixed; top: 1rem; right: 1rem; display: flex; gap: .5rem; }}
 #bar button {{ padding: .6rem 1rem; }}
 #count {{ align-self: center; color: #333; }}
</style>
<div id="bar">
  <span id="count"></span>
  <button id="copy">Copy picks JSON</button>
  <button id="download">Download picks.json</button>
</div>
{''.join(cards)}
<script>
function collect() {{
  const approved = [], rejected = [];
  for (const s of document.querySelectorAll('section[data-key]')) {{
    const sel = s.querySelector('input:checked');
    if (!sel) continue;
    (sel.value === 'approve' ? approved : rejected).push(s.dataset.key);
  }}
  return {{ approved, rejected }};
}}
function refresh() {{
  const p = collect();
  document.getElementById('count').textContent =
    `${{p.approved.length}} approved · ${{p.rejected.length}} rejected`;
}}
document.addEventListener('change', refresh);
document.getElementById('copy').onclick = async () => {{
  await navigator.clipboard.writeText(JSON.stringify(collect(), null, 2));
  const b = document.getElementById('copy');
  b.textContent = 'Copied!'; setTimeout(() => b.textContent = 'Copy picks JSON', 1200);
}};
document.getElementById('download').onclick = () => {{
  const blob = new Blob([JSON.stringify(collect(), null, 2)], {{type: 'application/json'}});
  const a = Object.assign(document.createElement('a'),
    {{ href: URL.createObjectURL(blob), download: 'picks.json' }});
  a.click();
}};
refresh();
</script>
"""
    path = out_base / "cut_gallery.html"
    path.write_text(page)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="*", help="folder names to process")
    ap.add_argument("--all", action="store_true",
                    help="process every index.json entry that has a PhotoPath")
    ap.add_argument("--root", default=str(REPO),
                    help="repo root holding index.json + the raw photos (default: repo)")
    ap.add_argument("--out-dir",
                    help="write cutouts + report here instead of alongside the raw photo")
    ap.add_argument("--margin", type=float, default=DEFAULT_MARGIN,
                    help=f"crop margin as fraction of the cutout's larger side (default {DEFAULT_MARGIN})")
    ap.add_argument("--sizes", default=",".join(map(str, DEFAULT_SIZES)),
                    help=f"comma-separated max dimensions (default {','.join(map(str, DEFAULT_SIZES))})")
    # isnet-general-use won the batch-1 bake-off: u2net ate thin structure
    # (solar panels, booms) on 6 of 22 photos; isnet rescued 5 of those.
    ap.add_argument("--model", default="isnet-general-use",
                    help="rembg model name (default isnet-general-use)")
    ap.add_argument("--cpu", action="store_true",
                    help="force onnxruntime's CPUExecutionProvider — macOS CoreML/ANE "
                         "compilation wedges indefinitely on very large models "
                         "(birefnet-general's 928 MB graph); plain CPU cuts in seconds")
    ap.add_argument("--force-matting", action="store_true",
                    help="run rembg even when the raw carries its own alpha channel "
                         "(default is to trust a source alpha — it's ground truth)")
    ap.add_argument("--gallery", action="store_true",
                    help="also write cut_gallery.html (before/after approval review)")
    ap.add_argument("--force", action="store_true", help="rebuild cutouts even if they exist")
    ap.add_argument("--allow-nonderiv", action="store_true",
                    help="override the flow-down guard and derive from media-terms/ND "
                         "photos (only after permission is confirmed)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out_base = Path(args.out_dir).resolve() if args.out_dir else root
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    index, by_folder = load_index(root)
    if args.all:
        folders = [f for f, e in by_folder.items() if e.get("PhotoPath")]
        if not folders:
            print("Nothing to do: no index.json entry has a PhotoPath under "
                  f"{root} (raw photos live on the batch PR branch — pass --root).")
            return 0
    else:
        folders = args.folders
    if not folders:
        ap.error("give one or more folder names, or --all")

    print(f"rembg {rembg_version()} · model {args.model} · margin {args.margin} · "
          f"sizes {sizes}\nroot {root}\nout  {out_base}\n")

    # the ONNX session takes seconds + ~170 MB to build; a run where every raw
    # carries its own alpha never needs it, so build lazily on first matting
    _session = []

    def get_session():
        if not _session:
            from rembg import new_session
            kwargs = {"providers": ["CPUExecutionProvider"]} if args.cpu else {}
            _session.append(new_session(args.model, **kwargs))
        return _session[0]

    report = {
        "tool": "tools/process_photos.py",
        "rembg_version": rembg_version(),
        "rembg_model": args.model,
        "margin": args.margin,
        "sizes": sizes,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "photos": [],
    }
    t_all = time.perf_counter()
    for folder in folders:
        rec = process_folder(folder, by_folder.get(folder), root, out_base,
                             get_session, args.model, sizes, args.margin, args.force,
                             args.allow_nonderiv, args.force_matting)
        if rec:
            report["photos"].append(rec)
    total = time.perf_counter() - t_all

    out_base.mkdir(parents=True, exist_ok=True)
    report_path = out_base / "cut_report.json"
    json.dump(report, open(report_path, "w"), indent=2)
    open(report_path, "a").write("\n")

    ok = sum(1 for p in report["photos"] if p["status"] == "ok")
    skipped = sum(1 for p in report["photos"] if p["status"].startswith("skipped"))
    failed = sum(1 for p in report["photos"] if p["status"].startswith("failed"))
    print(f"\n{ok} processed, {skipped} skipped, {failed} failed in {total:.1f}s")
    print(f"Wrote {report_path}")
    if args.gallery:
        gal = build_gallery(report, root, out_base)
        print(f"Wrote {gal} — open it, approve/reject, Copy picks JSON")
    return 0


if __name__ == "__main__":
    sys.exit(main())
