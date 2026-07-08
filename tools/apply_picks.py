#!/usr/bin/env python3
"""Apply gallery picks: download each chosen image and record its licence.

    python3 tools/apply_picks.py ~/Downloads/picks.json

For every pick this script:
  1. downloads the full-resolution file to satellites/<folder>/<folder>-photo.<ext>
  2. sets the entry's PhotoPath, imageSourceURL, imageRightsHolder,
     imageLicense, imageCredit in index.json and imageStatus to "licensed"
  3. adds/updates the file's row in ATTRIBUTIONS.csv

Review the git diff, then commit on a branch and open a PR.
"""

import csv
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UA = "satellite-visuals-curation/1.0 (https://github.com/eo-gos/satellite-visuals)"

picks = json.load(open(sys.argv[1]))
index = json.load(open(REPO / "index.json"))
by_folder = {e["SVGColourPath"].split("/")[1]: e for e in index}

rows = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
header, body = rows[0], rows[1:]
by_path = {r[0]: r for r in body}

for folder, pick in picks.items():
    entry = by_folder.get(folder)
    if entry is None:
        print(f"SKIP {folder}: no index.json entry")
        continue

    ext = pick["url"].rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "gif", "webp", "tif", "tiff"):
        ext = "jpg"
    rel = f"satellites/{folder}/{folder}-photo.{ext}"
    req = urllib.request.Request(pick["url"], headers={"User-Agent": UA})
    (REPO / rel).write_bytes(urllib.request.urlopen(req, timeout=60).read())

    rights = pick.get("artist") or pick.get("credit") or ""
    entry["PhotoPath"] = rel
    entry["imageSourceURL"] = pick.get("page") or pick["url"]
    entry["imageRightsHolder"] = rights or entry.get("imageRightsHolder", "")
    entry["imageLicense"] = pick["licence"]
    entry["imageCredit"] = pick.get("credit") or rights
    entry["imageStatus"] = "licensed"

    row = [rel, pick.get("title", ""), rights, entry["imageSourceURL"],
           pick["licence"], pick.get("page", "")]
    if rel in by_path:
        by_path[rel][:] = row
    else:
        body.append(row)
        by_path[rel] = row
    print(f"OK   {folder}: {rel} ({pick['licence']})")

# keep every entry carrying the PhotoPath key so the schema stays uniform
for e in index:
    e.setdefault("PhotoPath", "")

json.dump(index, open(REPO / "index.json", "w"), indent=2)
open(REPO / "index.json", "a").write("\n")
body.sort(key=lambda r: r[0])
with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(header)
    w.writerows(body)
print("\nindex.json + ATTRIBUTIONS.csv updated — review `git diff`, commit on a branch.")
