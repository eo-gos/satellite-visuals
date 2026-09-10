#!/usr/bin/env python3
"""Apply approved house artwork: copy the SVGs in, write the paperwork.

    python3 tools/apply_art.py ~/Downloads/art-picks.json
    cd tools && npm install && node render_pngs.mjs     # PNG renders
    python3 tools/check_index.py
    git diff                                            # then branch, commit, PR

For each approved pick this:

  1. copies `<folder>.svg` and `<folder>-icon.svg` out of the gitignored working
     directory into `satellites/<folder>/` (an icon marked `drop` is not copied);
  2. creates or updates the index.json entry: `folder`, the artwork paths,
     `artStatus: house-generated`, and `references` — the list of URLs the
     description was written from;
  3. adds ATTRIBUTIONS.csv rows for each SVG: repo maintainers, CC BY 4.0, with
     a method note recording that it is an original depiction drawn from
     reference imagery rather than traced from it.

**Reference images are never copied into the repository.** Only their URLs
travel, and a folder whose description carries none is refused: an original
depiction with no record of what was looked at cannot be reviewed, and the
`references` list is what makes golden rule 6 auditable after the fact.

PNG renders are deliberately NOT produced here. `render_pngs.mjs` is the one
place that turns our SVGs into the committed rasters, and it runs over the whole
tree; this tool prints the command rather than duplicating it.
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from house_art import schema  # noqa: E402
from house_art.refs import OUT  # noqa: E402
from index_utils import (UnsafeFolderName, by_folder, check_folder_name,  # noqa: E402
                         ensure_entry, load_index, save_index)

REPO = Path(__file__).resolve().parent.parent

ART_STATUS = "house-generated"
ART_LICENCE = "CC BY 4.0"
ART_HOLDER = "repo maintainers"
ART_SOURCE = "https://github.com/eo-gos/satellite-visuals"
METHOD_NOTE = ("original depiction drawn from a structured description via "
               "tools/house_art (golden rule 6); reference imagery consulted, "
               "never traced, and not stored in this repository")


class Refused(Exception):
    """A pick that must not be applied."""


def load_picks(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    picks = payload.get("picks", payload if isinstance(payload, list) else [])
    return [p for p in picks if p.get("decision") == "approve"]


def read_description(folder, workdir=None):
    base = Path(workdir or OUT) / folder
    path = base / "description.json"
    if not path.exists():
        raise Refused(f"{folder}: no description.json in {base}")
    d = json.loads(path.read_text(encoding="utf-8"))
    problems = schema.validate(d, folder)
    if problems:
        raise Refused(f"{folder}: description invalid — {'; '.join(problems)}")
    urls = schema.reference_urls(d)
    if not urls:
        raise Refused(f"{folder}: description carries no reference URLs — an "
                      f"original depiction must record what was looked at")
    return d, urls


def apply_one(folder, pick, index, attrib_rows, repo=REPO, workdir=None, dry_run=False):
    """Returns a list of human-readable actions. Raises Refused to skip."""
    folder = check_folder_name(folder)
    d, urls = read_description(folder, workdir)

    base = Path(workdir or OUT) / folder
    colour_src = base / f"{folder}.svg"
    icon_src = base / f"{folder}-icon.svg"
    if not colour_src.exists():
        raise Refused(f"{folder}: no {folder}.svg in {base}")

    keep_icon = pick.get("icon") != "drop" and icon_src.exists()
    dest = Path(repo) / "satellites" / folder
    colour_rel = f"satellites/{folder}/{folder}.svg"
    icon_rel = f"satellites/{folder}/{folder}-icon.svg"

    entry, created = ensure_entry(index, folder,
                                  str(d.get("mission_id") or ""),
                                  d.get("mission") or "")
    actions = []
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(colour_src, dest / colour_src.name)
        if keep_icon:
            shutil.copyfile(icon_src, dest / icon_src.name)

    entry["SVGColourPath"] = colour_rel
    entry["SVGBlackPath"] = icon_rel if keep_icon else ""
    # render_pngs.mjs writes these; record the paths it will produce so the
    # entry is complete the moment that command has run.
    entry["PNG1024Path"] = f"satellites/{folder}/{folder}-1024px.png"
    entry["PNG512Path"] = f"satellites/{folder}/{folder}-512px.png"
    entry["artStatus"] = ART_STATUS
    entry["references"] = urls
    entry.setdefault("PhotoPath", "")
    # A folder created by THIS lane exists because a licensed photo could not be
    # obtained, so it must not inherit the photo lane's "a photo is coming"
    # default. A folder that already has a photo (the ESA icon case) keeps its
    # photo fields untouched: this lane only ever adds artwork to those.
    if created and not entry.get("PhotoPath"):
        entry["imageStatus"] = "svg-fallback"
        entry["imageSourceTier"] = ""

    rows = [[colour_rel, f"{d.get('mission', folder)} (house artwork)", ART_HOLDER,
             ART_SOURCE, ART_LICENCE, METHOD_NOTE]]
    if keep_icon:
        rows.append([icon_rel, f"{d.get('mission', folder)} icon (house artwork)",
                     ART_HOLDER, ART_SOURCE, ART_LICENCE,
                     f"{METHOD_NOTE}; silhouette derived from {folder}.svg"])
    for row in rows:
        existing = attrib_rows.get(row[0])
        if existing is not None:
            existing[:] = row
        else:
            attrib_rows[row[0]] = row

    actions.append(f"{'NEW ' if created else 'OK  '} {folder}: {colour_rel}"
                   + (f" + icon" if keep_icon else " (icon dropped)")
                   + f", {len(urls)} reference URL(s), evidence {d.get('evidence')}")
    return actions


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("picks", help="art-picks.json exported from the checker")
    ap.add_argument("--workdir", default=None,
                    help=f"candidate directory (default {OUT})")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    picks = load_picks(args.picks)
    if not picks:
        print("no approved picks in that file")
        return 0

    index = load_index(REPO)
    rows = list(csv.reader(open(REPO / "ATTRIBUTIONS.csv")))
    header, body = rows[0], rows[1:]
    attrib_rows = {r[0]: r for r in body}
    before = set(by_folder(index))

    applied, refused = 0, 0
    for pick in picks:
        folder = pick.get("folder", "")
        try:
            for line in apply_one(folder, pick, index, attrib_rows,
                                  workdir=args.workdir, dry_run=args.dry_run):
                print(line)
            applied += 1
        except (Refused, UnsafeFolderName) as exc:
            print(f"REFUSED {exc}")
            refused += 1

    if args.dry_run:
        print(f"\ndry run: {applied} would apply, {refused} refused; nothing written")
        return 1 if refused else 0

    # A folder created by this run but refused before it got artwork must not be
    # persisted: an entry with no SVG and no rows reads as covered when it is not.
    keep = {f for f in by_folder(index) if by_folder(index)[f].get("SVGColourPath")}
    index[:] = [e for e in index
                if e.get("folder") in before or e.get("folder") in keep]

    save_index(index, REPO)
    merged = sorted(attrib_rows.values(), key=lambda r: r[0])
    with open(REPO / "ATTRIBUTIONS.csv", "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(merged)

    print(f"\n{applied} folder(s) applied"
          + (f", {refused} refused" if refused else "")
          + ".\nNext: cd tools && npm install && node render_pngs.mjs"
          + "\n      python3 tools/check_index.py"
          + "\n      git diff  — then branch, commit, PR.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
