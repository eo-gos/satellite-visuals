#!/usr/bin/env python3
"""Apply reviewed picks: ESA clean renders (crop + resize) + ordinary photo picks.

    python3 tools/apply_clean.py ~/Downloads/picks.json
    python3 tools/apply_clean.py ~/Downloads/picks.json --dry-run

Input is the picks.json exported by tools/make_checker.py:

    {"schema": "satellite-visuals/picks/2",
     "esa_clean": {"<folder>": {url, page, title, credit, rights_holder,
                                licence, status, licence_notice_url?}},
     "photos":    {"<folder>": {url, page, title, artist, credit, licence}}}

The two blocks are different lanes and are handled differently.

**esa_clean — ESA's own clean render.** ESA refused background removal in
writing (ESA HQ PHOTOS 20260819-0333); the portal's cut-out slot is therefore
filled from ESA's published clean version instead. This script downloads that
file untouched as `<folder>-photo-clean.<ext>` and derives the display sizes
`<folder>-photo-clean-1024px.png` / `-512px.png` by **cropping and scaling
only** — Lanczos resample, alpha preserved, never upscaled, no matting, no
compositing. ESA's ruling permits cropping, aspect-ratio change and resizing
and refuses only background removal, so an optional `crop` is allowed: give a
pick a `"crop": [x, y, w, h]` in pixels of the archival original (or
`--crop <folder>=x,y,w,h`) and the display PNGs are cut from that box before
scaling. The archival file is always stored exactly as published. There is
deliberately no flag for anything beyond crop and scale: this file must never
grow a background-removal path.

Paperwork written per folder:
  index.json   PhotoCleanPath / PhotoClean1024Path / PhotoClean512Path,
               imageSourceURL, imageRightsHolder, imageLicense, imageCredit,
               imageStatus, and licenceNoticeUrl **only** when the licence
               recorded is the ESA Standard Licence (check_index.py enforces
               that invariant in both directions).
  ATTRIBUTIONS one row per file on disk; the two PNGs record the crop box
               (when there is one) and the scale.

If a folder has no raw photo yet, the clean render simply becomes its only
committed image — PhotoPath is left alone rather than duplicating the file.

**photos — ordinary sourced photo.** Delegated unchanged to
tools/apply_picks.py, which downloads the raw and writes its paperwork. Those
files stay cuttable; the ESA prohibition does not apply to them.

Afterwards: `python3 tools/check_index.py`, then review `git diff`.
"""

import argparse
import csv
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_utils import (UnsafeFolderName, drop_entries, ensure_entry,  # noqa: E402
                         folder_of, load_index, parse_new_specs, save_index,
                         unbacked_folders)
from licenses import _norm  # noqa: E402  (local sibling module)

REPO = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent
UA = "satellite-visuals-curation/1.0 (https://github.com/eo-gos/satellite-visuals)"
NOTICE_URL = "https://www.esa.int/ESA_Multimedia/Copyright_Notice_Images"
SIZES = (1024, 512)

# Licences a clean render may be recorded under. ESA image pages offer either
# the Standard Licence or, on some pages, CC BY-SA 3.0 IGO; ASSET-LICENSING
# prefers the CC option where a page offers both, so both are accepted here.
ALLOWED = {"esa standard licence", "cc by-sa 3.0 igo"}
EXTS = ("jpg", "jpeg", "png", "tif", "tiff", "webp")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def crop_box_of(pick, size):
    """Validate a pick's crop box against the original's (width, height).
    Returns (x, y, w, h) or None. Raises ValueError if the box leaves the image
    — silently clamping would ship a different crop than the reviewer
    approved. Checked before anything is written, so a bad box leaves no
    archival file and no folder behind."""
    crop = pick.get("crop")
    if not crop:
        return None
    try:
        x, y, w, h = (int(v) for v in crop)
    except (TypeError, ValueError):
        raise ValueError(f"crop must be four integers [x, y, w, h], got {crop!r}")
    if w <= 0 or h <= 0:
        raise ValueError(f"crop width and height must be positive, got {w}x{h}")
    iw, ih = size
    if x < 0 or y < 0 or x + w > iw or y + h > ih:
        raise ValueError(f"crop [{x}, {y}, {w}, {h}] extends outside the "
                         f"{iw}x{ih} original")
    return x, y, w, h


def resize_only(src: Path, dest: Path, box: int, crop=None) -> str:
    """Crop (optional) then scale src to fit box on its long edge, save as PNG.
    Never upscales, never mattes, never touches pixels other than by cropping
    and resampling."""
    from PIL import Image
    im = Image.open(src)
    if im.mode not in ("RGBA", "LA", "RGB", "L", "P"):
        im = im.convert("RGBA")
    if im.mode == "P":
        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
    cropped = ""
    if crop:
        cx, cy, cw, ch = crop
        im = im.crop((cx, cy, cx + cw, cy + ch))
        cropped = f"cropped to {cx},{cy},{cw},{ch} of the original, then "
    w, h = im.size
    if max(w, h) > box:
        scale = box / max(w, h)
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                       Image.LANCZOS)
        how = f"{cropped}scaled to {im.size[0]}x{im.size[1]}"
    else:
        how = (f"{cropped}kept at {w}x{h} "
               f"(source smaller than {box}px; never upscaled)")
    im.save(dest, "PNG")
    return how


def load_csv():
    rows = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
    return rows[0], rows[1:]


def write_csv(header, body):
    body.sort(key=lambda r: r[0])
    with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)


def apply_esa_clean(picks, dry_run, new_folders=None):
    index = load_index()
    by_folder = {folder_of(e): e for e in index if folder_of(e)}
    header, body = load_csv()
    by_path = {r[0]: r for r in body}
    touched = 0

    # A licensed clean render alone makes a valid folder — no SVG required. The
    # entry is built in memory only; nothing is persisted until the folder's
    # pick has actually applied (CX P2).
    created_folders = set()
    for folder, spec in (new_folders or {}).items():
        # Validated before anything touches the filesystem (see apply_picks).
        try:
            entry, created = ensure_entry(index, folder, spec.get("missionID", ""),
                                          spec.get("missionName", ""))
        except UnsafeFolderName as exc:
            sys.exit(f"REFUSED {exc}")
        by_folder[folder] = entry
        if created:
            created_folders.add(folder)
        print(f"{'NEW ' if created else 'HAVE'} {folder}: photo-only entry pending "
              f"(missionID {entry['missionID'] or '—'})"
              + ("  (dry run — not written)" if dry_run else ""))

    applied, failed = set(), set()
    for folder, pick in picks.items():
        entry = by_folder.get(folder)
        if entry is None:
            print(f"SKIP {folder}: no index.json entry — pass "
                  f"--new folder={folder} missionID=... to create one")
            continue
        licence = pick.get("licence", "")
        if _norm(licence) not in ALLOWED:
            print(f"SKIP {folder}: licence {licence!r} is not one this lane accepts "
                  f"({', '.join(sorted(ALLOWED))})")
            continue

        # a download URL may carry a tracking query whose last dot-segment is
        # not a file extension — read the extension off the path, fetch clean
        url = pick["url"].split("?")[0].split("#")[0]
        ext = (pick.get("ext") or "").lower()
        if ext not in EXTS:
            ext = url.rsplit(".", 1)[-1].lower()
        if ext not in EXTS:
            ext = "jpg"
        rel = f"satellites/{folder}/{folder}-photo-clean.{ext}"
        dest = REPO / rel
        print(f"\n{folder}: {pick['title']}")
        print(f"  licence  {licence}")
        print(f"  archival {rel}")
        if dry_run:
            print("  (dry run — nothing written)")
            continue

        # Fetch first, then create the directory and write: a failed download
        # must not leave an empty folder behind.
        try:
            payload = fetch(url)
        except Exception as exc:
            print(f"  FAIL download failed ({exc}) — no file, no entry")
            failed.add(folder)
            continue

        # Validate the crop against the bytes in hand, before anything reaches
        # the filesystem: a bad box must not leave an archival file or a folder.
        try:
            import io as _io
            from PIL import Image as _Image
            with _Image.open(_io.BytesIO(payload)) as probe:
                crop = crop_box_of(pick, probe.size)
        except ValueError as exc:
            print(f"  FAIL {exc} — nothing written")
            failed.add(folder)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)

        derived = []
        for box in SIZES:
            drel = f"satellites/{folder}/{folder}-photo-clean-{box}px.png"
            how = resize_only(dest, REPO / drel, box, crop)
            derived.append((drel, how))
            print(f"  display  {drel}  ({how})")

        entry["PhotoCleanPath"] = rel
        entry["PhotoClean1024Path"] = derived[0][0]
        entry["PhotoClean512Path"] = derived[1][0]
        entry["imageSourceURL"] = pick.get("page") or url
        entry["imageRightsHolder"] = pick.get("rights_holder") or pick.get("credit", "")
        entry["imageLicense"] = licence
        entry["imageCredit"] = pick.get("credit", "")
        # Tier B by definition: this lane is an agency multimedia page whose
        # published terms permit the use (ASSET-LICENSING's tier vocabulary).
        entry["imageSourceTier"] = pick.get("tier", "B")
        entry["imageStatus"] = pick.get("status", "licensed")
        if _norm(licence) == "esa standard licence":
            entry["licenceNoticeUrl"] = NOTICE_URL
        elif "licenceNoticeUrl" in entry:
            # check_index.py fails if the notice field survives on a non-ESA
            # licence, so dropping it is required, not tidying. Say so loudly:
            # the raw photo in this folder may still be under the ESA Standard
            # Licence, and its own ATTRIBUTIONS row keeps recording that.
            del entry["licenceNoticeUrl"]
            print("  NOTE   licenceNoticeUrl removed — this entry is now recorded under "
                  f"{licence}. Check any raw photo in the same folder: its ATTRIBUTIONS "
                  "row still carries its own licence, and the display layer reads the "
                  "notice condition from index.json.")

        note_base = (f"ESA official clean render, taken as published. "
                     f"Source page: {entry['imageSourceURL']}")
        rows = [(rel, note_base)]
        rows += [(drel, f"display copy of {Path(rel).name} — {how}; "
                        f"no other change: no matting, no background edits "
                        f"(tools/apply_clean.py)")
                 for drel, how in derived]
        for path, note in rows:
            row = [path, pick.get("title", ""), entry["imageRightsHolder"],
                   entry["imageSourceURL"], licence, note]
            if path in by_path:
                by_path[path][:] = row
            else:
                body.append(row)
                by_path[path] = row
        touched += 1
        applied.add(folder)

    # CX P2: a folder created by this run without an applied pick is dropped —
    # an entry with no file and no ATTRIBUTIONS row reads as covered when it is
    # not.
    unbacked = unbacked_folders(created_folders, applied)
    if unbacked:
        drop_entries(index, unbacked)
        for folder in unbacked:
            why = "its pick failed" if folder in failed else \
                  "no pick in this file matched it"
            print(f"DROP {folder}: {why} — entry not written, no folder created")
    if failed:
        print(f"FAIL {len(failed)} clean pick(s) failed: {', '.join(sorted(failed))}")

    if (touched or (created_folders - set(unbacked))) and not dry_run:
        for e in index:
            e.setdefault("PhotoPath", "")
        save_index(index)
        write_csv(header, body)
    # Hand the unbacked state back: main() decides the exit code, the same way
    # apply_picks does for its own lane. Reporting a drop and returning a count
    # that looks like success is how a failed download reads as a clean run.
    return touched, set(unbacked), set(failed)


def apply_photos(picks, new_folders, dry_run):
    """Hand the ordinary-photo block to apply_picks.py, WITH the new_folders
    that belong to it — without them apply_picks skips every folder that does
    not exist yet, which is the whole point of a photo-lane new folder."""
    if not picks and not new_folders:
        return 0, True
    if dry_run:
        print(f"\n(dry run) would run apply_picks.py for: {', '.join(sorted(picks))}"
              + (f" (creating {', '.join(sorted(new_folders))})" if new_folders else ""))
        return 0, True
    payload = {"schema": "satellite-visuals/picks/2", "photos": picks}
    if new_folders:
        payload["new_folders"] = new_folders
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        tmp = f.name
    print(f"\nphotos block -> tools/apply_picks.py ({len(picks)} folders"
          + (f", {len(new_folders)} new" if new_folders else "") + ")")
    result = subprocess.run([sys.executable, str(TOOLS / "apply_picks.py"), tmp])
    # apply_picks exits non-zero when a pick failed or a requested folder ended
    # unbacked. Report that as a failed lane rather than raising
    # CalledProcessError, which would bury the reason under a traceback.
    return len(picks), result.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("picks", help="picks.json exported by tools/make_checker.py")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    ap.add_argument("--crop", action="append", metavar="FOLDER=X,Y,W,H",
                    help="crop the display copies to this box of the archival "
                         "original before scaling (ESA permits cropping); the "
                         "archival file is always stored unmodified")
    ap.add_argument("--new", nargs="+", action="append", metavar="KEY=VALUE",
                    help="create a folder that has no index entry yet: "
                         "--new folder=<name> missionID=<id> missionName=<name> "
                         "(repeat the flag per folder)")
    args = ap.parse_args()

    data = json.load(open(args.picks))
    if "esa_clean" not in data and "photos" not in data:
        sys.exit("This file has neither an esa_clean nor a photos block. A flat "
                 "folder->pick mapping is the older shape — feed it to "
                 "tools/apply_picks.py instead.")

    try:
        new_folders = dict(parse_new_specs(args.new))
    except UnsafeFolderName as exc:
        sys.exit(f"REFUSED {exc}")
    for folder, spec in (data.get("new_folders") or {}).items():
        new_folders.setdefault(folder, spec)

    # Route each new folder to the lane that actually holds its pick. Handing
    # the whole block to the clean pass made it drop every photo-lane folder as
    # unbacked, and the photos pass then never saw them — so a valid public
    # domain photo for a folder that does not exist yet was silently skipped.
    for spec in (args.crop or []):
        folder, _, box = spec.partition("=")
        try:
            data.setdefault("esa_clean", {}).setdefault(folder, {})["crop"] = \
                [int(v) for v in box.split(",")]
        except ValueError:
            sys.exit(f"REFUSED --crop expects FOLDER=x,y,w,h, got {spec!r}")

    clean_picks = data.get("esa_clean", {})
    photo_picks = data.get("photos", {})
    clean_new = {f: s for f, s in new_folders.items() if f in clean_picks}
    photo_new = {f: s for f, s in new_folders.items() if f in photo_picks}
    orphans = sorted(set(new_folders) - set(clean_new) - set(photo_new))
    for folder in orphans:
        print(f"DROP {folder}: requested as a new folder but no pick in either "
              f"lane names it — entry not written, no folder created")

    n_clean, clean_unbacked, clean_failed = apply_esa_clean(
        clean_picks, args.dry_run, clean_new)
    n_photo, photos_ok = apply_photos(photo_picks, photo_new, args.dry_run)

    dropped = sorted(set(orphans) | clean_unbacked)
    print(f"\n{n_clean} clean render(s), {n_photo} photo pick(s)."
          + (f" {len(dropped)} unbacked new folder(s) dropped." if dropped else ""))
    if not args.dry_run:
        print("Next: python3 tools/check_index.py, then review `git diff` and commit "
              "on a branch.")

    # Cleanup has already happened; the exit code is what tells a caller the
    # file did not fully apply. Every lane reports, so a failure in either one
    # fails the command.
    problems = []
    if dropped:
        problems.append(f"{len(dropped)} requested folder(s) not created: "
                        f"{', '.join(dropped)}")
    if clean_failed:
        problems.append(f"{len(clean_failed)} clean pick(s) failed: "
                        f"{', '.join(sorted(clean_failed))}")
    if not photos_ok:
        problems.append("the photo lane reported failures (see above)")
    if problems:
        sys.exit("; ".join(problems))


if __name__ == "__main__":
    main()
