#!/usr/bin/env python3
"""Apply gallery picks: download each chosen image and record its licence.

    python3 tools/apply_picks.py ~/Downloads/picks.json

For every pick this script:
  1. downloads the full-resolution file to satellites/<folder>/<folder>-photo.<ext>
  2. sets the entry's PhotoPath, imageSourceURL, imageRightsHolder,
     imageLicense, imageCredit in index.json and imageStatus to "licensed"
  3. adds/updates the file's row in ATTRIBUTIONS.csv

Review the git diff, then commit on a branch and open a PR.

Two input shapes are accepted: the flat ``{folder: pick}`` mapping exported by
make_gallery.py, and the ``{"photos": {folder: pick}, ...}`` wrapper exported by
make_checker.py — whose sibling ``esa_clean`` block is a different lane and is
ignored here (tools/apply_clean.py owns it, and would refuse to cut anyway).
"""

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index_utils import (UnsafeFolderName, drop_entries, ensure_entry,  # noqa: E402
                         folder_of, load_index, parse_new_specs, save_index,
                         unbacked_folders)
from process_photos import photo_crop_of  # noqa: E402  (shared crop validator)

REPO = Path(__file__).resolve().parent.parent
UA = "satellite-visuals-curation/1.0 (https://github.com/eo-gos/satellite-visuals)"

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("picks", help="picks.json")
_ap.add_argument("--new", nargs="+", action="append", metavar="KEY=VALUE",
                 help="create a folder that has no index entry yet: "
                      "--new folder=<name> missionID=<id> missionName=<name> "
                      "(repeat the flag per folder)")
_args = _ap.parse_args()

picks = json.load(open(_args.picks))
try:
    new_folders = dict(parse_new_specs(_args.new))
except UnsafeFolderName as exc:
    sys.exit(f"REFUSED {exc}")
if isinstance(picks, dict) and ("photos" in picks or "esa_clean" in picks):
    if picks.get("esa_clean"):
        print(f"NOTE {len(picks['esa_clean'])} esa_clean pick(s) in this file are not "
              f"this tool's lane — run tools/apply_clean.py for those.")
    for folder, spec in (picks.get("new_folders") or {}).items():
        new_folders.setdefault(folder, spec)
    picks = picks.get("photos", {})
index = load_index()
by_folder = {folder_of(e): e for e in index if folder_of(e)}

# A licensed photo alone makes a valid folder now — no SVG required, so a pick
# may create its folder. The entry is built in memory only: nothing is written
# to disk, and no new entry is persisted, until that folder's pick has actually
# applied. An entry with no photo and no ATTRIBUTIONS row is not a folder, it is
# a hole in the index.
created_folders = set()
for folder, spec in new_folders.items():
    # Validated before anything touches the filesystem: a path-like value would
    # otherwise mkdir and write outside satellites/.
    try:
        entry, created = ensure_entry(index, folder, spec.get("missionID", ""),
                                      spec.get("missionName", ""))
    except UnsafeFolderName as exc:
        sys.exit(f"REFUSED {exc}")
    by_folder[folder] = entry
    if created:
        created_folders.add(folder)
    print(f"{'NEW ' if created else 'HAVE'} {folder}: photo-only entry pending "
          f"(missionID {entry['missionID'] or '—'})")

rows = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
header, body = rows[0], rows[1:]
by_path = {r[0]: r for r in body}

applied, failed = set(), set()
for folder, pick in picks.items():
    entry = by_folder.get(folder)
    if entry is None:
        print(f"SKIP {folder}: no index.json entry")
        continue

    # Wikimedia download URLs carry a tracking query whose last dot-segment is
    # not a file extension ("...png?utm_source=commons.wikimedia.org&...").
    # Take the extension from the path and fetch the URL without the query.
    url = pick["url"].split("?")[0].split("#")[0]
    ext = (pick.get("ext") or "").lower()
    if ext not in ("jpg", "jpeg", "png", "gif", "webp", "tif", "tiff"):
        ext = url.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "gif", "webp", "tif", "tiff"):
        ext = "jpg"
    rel = f"satellites/{folder}/{folder}-photo.{ext}"
    # Download into memory first, then create the directory and write. A failed
    # download must not leave an empty folder behind.
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        payload = urllib.request.urlopen(req, timeout=60).read()
    except Exception as exc:
        print(f"FAIL {folder}: download failed ({exc}) — no file, no entry")
        failed.add(folder)
        continue
    # Validate the crop against the decoded bytes BEFORE anything reaches the
    # filesystem. Writing first and validating after leaves an untracked raw
    # behind when the box is bad — the folder then looks half-made on disk
    # while the index says nothing about it.
    crop = pick.get("crop")
    crop_value = None
    if crop:
        import io as _io
        from PIL import Image as _Image
        try:
            with _Image.open(_io.BytesIO(payload)) as probe:
                crop_value = list(photo_crop_of(None, probe.size, crop))
        except Exception as exc:
            print(f"FAIL {folder}: {exc} — no file, no entry")
            failed.add(folder)
            continue

    (REPO / rel).parent.mkdir(parents=True, exist_ok=True)
    (REPO / rel).write_bytes(payload)

    # rights_holder / credit, when the pick carries them, are the curated
    # values and win: a source's own metadata field is not always a credit
    # (Commons puts the Flickr photo title in "Credit").
    rights = pick.get("rights_holder") or pick.get("artist") or pick.get("credit") or ""
    entry["PhotoPath"] = rel
    entry["imageSourceURL"] = pick.get("page") or url
    entry["imageRightsHolder"] = rights or entry.get("imageRightsHolder", "")
    entry["imageLicense"] = pick["licence"]
    entry["imageCredit"] = pick.get("credit") or rights
    entry["imageStatus"] = pick.get("status", "licensed")
    # A pre-cut crop box travels with the entry so the cut pass can honour it.
    # The raw file above is stored exactly as published; this only narrows what
    # the cutter looks at. Already validated, above, before any write.
    if crop_value:
        entry["photoCrop"] = crop_value
    elif "photoCrop" in entry:
        del entry["photoCrop"]

    row = [rel, pick.get("title", ""), rights, entry["imageSourceURL"],
           pick["licence"], pick.get("notes") or pick.get("page", "")]
    if rel in by_path:
        by_path[rel][:] = row
    else:
        body.append(row)
        by_path[rel] = row
    applied.add(folder)
    print(f"OK   {folder}: {rel} ({pick['licence']})")

# CX P2: a folder this run created must have an applied pick, or it does not
# get persisted. Drop the entry, leave the tree alone, and say so — a half-made
# folder is worse than no folder, because it reads as covered.
unbacked = unbacked_folders(created_folders, applied)
if unbacked:
    drop_entries(index, unbacked)
    for folder in unbacked:
        why = "its pick failed" if folder in failed else "no pick in this file matched it"
        print(f"DROP {folder}: {why} — entry not written, no folder created")

# keep every entry carrying the PhotoPath key so the schema stays uniform
for e in index:
    e.setdefault("PhotoPath", "")

save_index(index)
body.sort(key=lambda r: r[0])
with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(body)
print(f"\n{len(applied)} pick(s) applied"
      + (f", {len(unbacked)} unbacked folder(s) dropped" if unbacked else "")
      + ".\nindex.json + ATTRIBUTIONS.csv updated — review `git diff`, commit on a branch.")
# A requested folder that ends unbacked is a failed run, whether the download
# broke or no pick ever named it. Cleanup happened above; the exit code is what
# tells a caller (or apply_clean's subprocess) that the file did not fully
# apply — printing DROP and exiting 0 reads as success.
if unbacked or failed:
    problems = sorted(set(unbacked) | failed)
    sys.exit(f"{len(problems)} requested folder(s) did not apply: "
             f"{', '.join(problems)}")
